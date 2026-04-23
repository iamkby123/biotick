"""Admin endpoints for comping Pro subscriptions + user management.

Gated by `require_admin_user`, which verifies a Supabase JWT AND looks up
the caller's `profiles.is_admin` flag. This is separate from the older
`X-Admin-Key` header used on `/api/sync/*` — that's for ops; this is for
the logged-in admin web UI.

Security posture:
- Admins can grant/revoke the 'pro' plan on any user account.
- Every grant/revoke is logged to `admin_audit`.
- Admin-granted pro subs set `comp_granted=TRUE`, so the Stripe
  webhook's subscription-cancelled handler won't unintentionally demote
  them (see `stripe_webhook.py`).
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import _decode_token
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Auth dependency ─────────────────────────────────────────────────────


async def require_admin_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Require a valid Supabase JWT AND `profiles.is_admin = true`.

    Returns the admin's {id, email} dict for use in audit logging.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Token missing sub claim")

    row = (
        await db.execute(
            text("SELECT id, email, is_admin FROM profiles WHERE id = :uid"),
            {"uid": user_id},
        )
    ).fetchone()
    if not row or not row[2]:
        # Same response whether profile doesn't exist or is_admin=false —
        # we don't leak which users have profiles to random callers.
        raise HTTPException(403, "Admin access required")
    return {"id": str(row[0]), "email": row[1]}


# ─── Request models ──────────────────────────────────────────────────────


class GrantProBody(BaseModel):
    email: str
    note: str | None = None


class RevokeProBody(BaseModel):
    email: str
    note: str | None = None


# ─── Helpers ─────────────────────────────────────────────────────────────


async def _find_user_by_email(db: AsyncSession, email: str) -> dict | None:
    row = (
        await db.execute(
            text(
                "SELECT u.id, u.email, p.plan, p.is_admin, p.comp_granted, p.stripe_customer_id "
                "FROM auth.users u LEFT JOIN profiles p ON p.id = u.id "
                "WHERE lower(u.email) = lower(:e)"
            ),
            {"e": email.strip()},
        )
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "email": row[1],
        "plan": row[2] or "free",
        "is_admin": bool(row[3]) if row[3] is not None else False,
        "comp_granted": bool(row[4]) if row[4] is not None else False,
        "stripe_customer_id": row[5],
    }


async def _log_audit(
    db: AsyncSession,
    admin_id: str,
    action: str,
    target_user_id: str | None = None,
    target_email: str | None = None,
    details: dict | None = None,
):
    await db.execute(
        text(
            "INSERT INTO admin_audit (admin_id, target_user_id, target_email, action, details) "
            "VALUES (:admin_id, :target_user_id, :target_email, :action, CAST(:details AS jsonb))"
        ),
        {
            "admin_id": admin_id,
            "target_user_id": target_user_id,
            "target_email": target_email,
            "action": action,
            "details": _json_dumps(details or {}),
        },
    )


def _json_dumps(d: dict) -> str:
    import json

    return json.dumps(d, default=str)


# ─── Routes ──────────────────────────────────────────────────────────────


@router.get("/me")
async def admin_me(admin: dict = Depends(require_admin_user)):
    """Return `{is_admin: true}` if the caller is an admin. Used by the
    frontend to decide whether to render the admin sidebar link."""
    return {"is_admin": True, "email": admin["email"]}


@router.post("/grant-pro")
async def grant_pro(
    body: GrantProBody,
    admin: dict = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Flip a user's plan to 'pro' without requiring a Stripe subscription.

    `comp_granted=TRUE` prevents the Stripe webhook's cancelled-subscription
    handler from accidentally downgrading them later.
    """
    target = await _find_user_by_email(db, body.email)
    if not target:
        raise HTTPException(404, f"No user with email {body.email}")

    await db.execute(
        text(
            "UPDATE profiles SET plan='pro', comp_granted=TRUE, updated_at=now() "
            "WHERE id = :uid"
        ),
        {"uid": target["id"]},
    )
    await _log_audit(
        db,
        admin_id=admin["id"],
        action="grant_pro",
        target_user_id=target["id"],
        target_email=target["email"],
        details={"note": body.note, "previous_plan": target["plan"]},
    )
    await db.commit()
    logger.info(
        f"Admin {admin['email']} granted pro to {target['email']} (was {target['plan']})"
    )
    return {
        "ok": True,
        "email": target["email"],
        "previous_plan": target["plan"],
        "new_plan": "pro",
    }


@router.post("/revoke-pro")
async def revoke_pro(
    body: RevokeProBody,
    admin: dict = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a comped pro subscription. Only revokes plans that were
    granted via admin (comp_granted=TRUE) — paying Stripe customers are
    left alone so we don't accidentally break real subs."""
    target = await _find_user_by_email(db, body.email)
    if not target:
        raise HTTPException(404, f"No user with email {body.email}")
    if not target["comp_granted"]:
        raise HTTPException(
            400,
            "This user's pro plan isn't admin-granted; cancel the Stripe "
            "subscription directly to revoke it.",
        )

    await db.execute(
        text(
            "UPDATE profiles SET plan='free', comp_granted=FALSE, updated_at=now() "
            "WHERE id = :uid"
        ),
        {"uid": target["id"]},
    )
    await _log_audit(
        db,
        admin_id=admin["id"],
        action="revoke_pro",
        target_user_id=target["id"],
        target_email=target["email"],
        details={"note": body.note},
    )
    await db.commit()
    logger.info(f"Admin {admin['email']} revoked pro from {target['email']}")
    return {"ok": True, "email": target["email"], "new_plan": "free"}


@router.get("/users")
async def list_users(
    search: str | None = None,
    plan: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List users, optionally filtered by email substring or plan.

    Useful for the admin UI to find an account before flipping its plan.
    """
    limit = max(1, min(200, limit))
    clauses = []
    params: dict = {"lim": limit, "off": max(0, offset)}
    if search:
        clauses.append("lower(u.email) LIKE '%' || lower(:q) || '%'")
        params["q"] = search
    if plan in ("free", "pro"):
        clauses.append("COALESCE(p.plan, 'free') = :plan")
        params["plan"] = plan
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
        SELECT u.id, u.email, COALESCE(p.plan, 'free') AS plan,
               COALESCE(p.is_admin, FALSE) AS is_admin,
               COALESCE(p.comp_granted, FALSE) AS comp_granted,
               p.stripe_customer_id, u.created_at
        FROM auth.users u
        LEFT JOIN profiles p ON p.id = u.id
        {where}
        ORDER BY u.created_at DESC
        LIMIT :lim OFFSET :off
    """
    rows = (await db.execute(text(sql), params)).fetchall()

    total_sql = f"SELECT COUNT(*) FROM auth.users u LEFT JOIN profiles p ON p.id = u.id {where}"
    total = (await db.execute(text(total_sql), {k: v for k, v in params.items() if k not in ('lim','off')})).scalar()

    return {
        "total": int(total or 0),
        "items": [
            {
                "id": str(r[0]),
                "email": r[1],
                "plan": r[2],
                "is_admin": bool(r[3]),
                "comp_granted": bool(r[4]),
                "stripe_customer_id": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ],
    }


@router.get("/audit")
async def audit_log(
    limit: int = 50,
    admin: dict = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent admin actions — who comped what, when."""
    limit = max(1, min(200, limit))
    rows = (
        await db.execute(
            text(
                "SELECT a.id, a.admin_id, u.email AS admin_email, a.target_email, "
                "       a.action, a.details, a.created_at "
                "FROM admin_audit a "
                "LEFT JOIN auth.users u ON u.id = a.admin_id "
                "ORDER BY a.created_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
    ).fetchall()
    return {
        "items": [
            {
                "id": r[0],
                "admin_email": r[2],
                "target_email": r[3],
                "action": r[4],
                "details": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ]
    }
