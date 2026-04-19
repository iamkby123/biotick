"""Authentication helpers.

Two flavours here:
  - X-Admin-Key header for /api/sync/* (server-to-server secret, used by
    the operator — that's just us for now).
  - Supabase JWT verification for user-scoped endpoints like
    /stripe/create-checkout. The Supabase anon/authenticated JWTs are
    HS256-signed with the project's JWT secret; we verify the signature
    and trust the `sub` claim as the user id.
"""

import os

import jwt
from fastapi import Header, HTTPException, status


# ─── Admin key (for sync endpoints) ─────────────────────────────────────

def _admin_key() -> str:
    return os.environ.get("ADMIN_API_KEY", "").strip()


async def require_admin_key(x_admin_key: str | None = Header(None, alias="x-admin-key")):
    """FastAPI dependency — 401s unless the request has a valid X-Admin-Key header.

    Fails closed: if ADMIN_API_KEY isn't set, all admin endpoints are rejected
    with 503 so we never accidentally expose them because of a missing env var.
    """
    expected = _admin_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API disabled (ADMIN_API_KEY not configured)",
        )
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Key header",
        )


# ─── Supabase JWT verification (for user endpoints) ─────────────────────

def _supabase_jwt_secret() -> str:
    return os.environ.get("SUPABASE_JWT_SECRET", "").strip()


async def get_current_user_id(authorization: str | None = Header(None)) -> str:
    """FastAPI dependency — returns the Supabase user id from a verified JWT.

    The frontend gets a JWT from Supabase on login and sends it in the
    Authorization header. We verify it was actually signed by Supabase
    (not forged) before trusting the user id claim.

    Fails closed: if SUPABASE_JWT_SECRET isn't set we reject all requests.
    """
    secret = _supabase_jwt_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User auth not configured (SUPABASE_JWT_SECRET missing)",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Token missing sub claim")
    return str(user_id)
