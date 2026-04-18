"""Stripe webhook for subscription lifecycle -> Supabase profiles.plan sync."""

import logging
import os
import json
import httpx

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel
import stripe

from app.database import async_session
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stripe", tags=["stripe"])

# Initialize Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Stripe Pro subscription price ID (from Payment Link product)
STRIPE_PRO_PRICE_ID = os.environ.get(
    "STRIPE_PRO_PRICE_ID", "price_1TMRwRHhLOSR40wWKZYGeOUp"
)

# Where Stripe sends the user after checkout completes / is cancelled.
SITE_URL = os.environ.get("SITE_URL", "https://biotick.io")

# Supabase admin (service role) — needed to update profiles
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bfhmaswnkzoowfxrsfce.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


async def _update_profile_by_id(user_id: str, plan: str, customer_id: str | None = None):
    """Update a user's plan in Supabase profiles by Supabase user id."""
    async with async_session() as db:
        try:
            # If customer_id is provided, set it; otherwise leave existing value intact.
            if customer_id:
                await db.execute(
                    text("""
                        UPDATE profiles
                        SET plan = :plan, stripe_customer_id = :cid, updated_at = now()
                        WHERE id = :uid
                    """),
                    {"plan": plan, "cid": customer_id, "uid": user_id},
                )
            else:
                await db.execute(
                    text("""
                        UPDATE profiles
                        SET plan = :plan, updated_at = now()
                        WHERE id = :uid
                    """),
                    {"plan": plan, "uid": user_id},
                )
            await db.commit()
            logger.info(f"Updated user_id={user_id} to plan={plan}")
            return True
        except Exception as e:
            logger.error(f"Failed to update user_id={user_id} to {plan}: {e}")
            await db.rollback()
            return False


async def _update_profile_by_customer_id(customer_id: str, plan: str):
    """Update a user's plan by Stripe customer ID (already linked to a profile)."""
    async with async_session() as db:
        try:
            result = await db.execute(
                text("""
                    UPDATE profiles
                    SET plan = :plan, updated_at = now()
                    WHERE stripe_customer_id = :cid
                    RETURNING id
                """),
                {"plan": plan, "cid": customer_id},
            )
            rows = result.fetchall()
            await db.commit()
            if rows:
                logger.info(f"Updated customer_id={customer_id} to plan={plan} ({len(rows)} row)")
                return True
            logger.warning(f"No profile with stripe_customer_id={customer_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to update customer_id={customer_id} to {plan}: {e}")
            await db.rollback()
            return False


async def update_user_plan(email: str, plan: str, customer_id: str | None = None):
    """Update a user's plan in Supabase profiles by email (legacy fallback)."""
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


class CreateCheckoutBody(BaseModel):
    user_id: str
    email: str | None = None


@router.post("/create-checkout")
async def create_checkout(body: CreateCheckoutBody):
    """Create a Stripe Checkout Session tied to a Supabase user_id.

    The client_reference_id makes the webhook match bulletproof — we don't have
    to guess which Biotick account goes with which Stripe customer based on email.
    """
    if not stripe.api_key:
        raise HTTPException(500, "Stripe not configured")
    if not body.user_id:
        raise HTTPException(400, "user_id is required")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRO_PRICE_ID, "quantity": 1}],
            client_reference_id=body.user_id,
            customer_email=body.email or None,
            success_url=f"{SITE_URL}/dashboard?upgraded=1",
            cancel_url=f"{SITE_URL}/",
            allow_promotion_codes=True,
            metadata={"supabase_user_id": body.user_id},
        )
        return {"url": session.url, "id": session.id}
    except Exception as e:
        logger.error(f"create-checkout failed for user {body.user_id}: {e}")
        raise HTTPException(500, str(e))


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
        mode = data.get("mode")
        if mode != "subscription":
            return {"received": True}

        # Preferred: client_reference_id is the Supabase user id we set when creating the session.
        # Fallback 1: metadata.supabase_user_id (same thing, different field).
        # Fallback 2: email (legacy Payment Links that don't carry a reference id).
        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("supabase_user_id")
        email = data.get("customer_details", {}).get("email") or data.get("customer_email")
        customer_id = data.get("customer")

        if user_id:
            await _update_profile_by_id(user_id, "pro", customer_id)
        elif email:
            logger.warning(f"No client_reference_id on checkout.session.completed; falling back to email={email}")
            await update_user_plan(email, "pro", customer_id)
        else:
            logger.error(f"checkout.session.completed with no user_id and no email: customer={customer_id}")

    # Subscription deleted / cancelled
    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        customer_id = data.get("customer")
        if not customer_id:
            return {"received": True}
        # Primary path: we already linked this customer_id to a profile, just flip plan to free.
        if not await _update_profile_by_customer_id(customer_id, "free"):
            # Fallback: look up email via Stripe and match that way.
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
        if not customer_id:
            return {"received": True}
        new_plan = "pro" if status in ("active", "trialing") else "free"
        if not await _update_profile_by_customer_id(customer_id, new_plan):
            try:
                cust = stripe.Customer.retrieve(customer_id)
                email = cust.get("email")
                if email:
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
