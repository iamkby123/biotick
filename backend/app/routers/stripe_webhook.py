"""Stripe webhook for subscription lifecycle -> Supabase profiles.plan sync."""

import logging
import os
import json
import httpx

from fastapi import APIRouter, Request, HTTPException, Header
import stripe

from app.database import async_session
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stripe", tags=["stripe"])

# Initialize Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Supabase admin (service role) — needed to update profiles
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bfhmaswnkzoowfxrsfce.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


async def update_user_plan(email: str, plan: str, customer_id: str | None = None):
    """Update a user's plan in Supabase profiles by email."""
    if not email:
        logger.warning("No email provided, skipping plan update")
        return False

    # Direct DB update via our Postgres connection
    async with async_session() as db:
        try:
            # Find the auth.users record by email (Supabase stores it there)
            # Then update public.profiles
            result = await db.execute(
                text("SELECT id FROM auth.users WHERE lower(email) = lower(:e)"),
                {"e": email},
            )
            user_row = result.fetchone()
            if not user_row:
                logger.warning(f"No user found for email {email}")
                return False

            user_id = str(user_row[0])

            # Update profile
            await db.execute(
                text("""
                    UPDATE profiles
                    SET plan = :plan, stripe_customer_id = :cid, updated_at = now()
                    WHERE id = :uid
                """),
                {"plan": plan, "cid": customer_id, "uid": user_id},
            )
            await db.commit()
            logger.info(f"Updated {email} ({user_id}) to plan={plan}")
            return True
        except Exception as e:
            logger.error(f"Failed to update {email} to {plan}: {e}")
            await db.rollback()
            return False


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
):
    """Handle Stripe webhook events."""
    payload = await request.body()

    # Verify signature
    if WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # Dev mode: parse without verification
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    logger.info(f"Stripe event: {event_type}")

    # Checkout completed — user paid for subscription
    if event_type == "checkout.session.completed":
        email = data.get("customer_details", {}).get("email") or data.get("customer_email")
        customer_id = data.get("customer")
        mode = data.get("mode")
        if mode == "subscription" and email:
            await update_user_plan(email, "pro", customer_id)

    # Subscription deleted / cancelled
    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        customer_id = data.get("customer")
        if customer_id:
            # Look up email from Stripe customer
            try:
                cust = stripe.Customer.retrieve(customer_id)
                email = cust.get("email")
                if email:
                    await update_user_plan(email, "free", customer_id)
            except Exception as e:
                logger.error(f"Failed to fetch customer {customer_id}: {e}")

    # Subscription updated (e.g., payment failed -> status=past_due)
    elif event_type == "customer.subscription.updated":
        status = data.get("status")
        customer_id = data.get("customer")
        if customer_id:
            try:
                cust = stripe.Customer.retrieve(customer_id)
                email = cust.get("email")
                if email:
                    new_plan = "pro" if status in ("active", "trialing") else "free"
                    await update_user_plan(email, new_plan, customer_id)
            except Exception as e:
                logger.error(f"Failed to fetch customer {customer_id}: {e}")

    return {"received": True}


@router.get("/status")
async def stripe_status():
    """Diagnostic endpoint."""
    return {
        "stripe_key_set": bool(stripe.api_key),
        "webhook_secret_set": bool(WEBHOOK_SECRET),
    }


@router.post("/sync-customer")
async def sync_customer_by_email(email: str):
    """Manually sync a Stripe customer's subscription status by email.
    Useful if a webhook was missed.
    """
    if not stripe.api_key:
        raise HTTPException(500, "Stripe not configured")
    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            return {"found": False, "message": "No Stripe customer for this email"}
        customer = customers.data[0]
        subs = stripe.Subscription.list(customer=customer.id, status="all", limit=5)
        active = any(s.status in ("active", "trialing") for s in subs.data)
        plan = "pro" if active else "free"
        updated = await update_user_plan(email, plan, customer.id)
        return {
            "found": True,
            "customer_id": customer.id,
            "subscription_statuses": [s.status for s in subs.data],
            "set_plan": plan,
            "updated": updated,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
