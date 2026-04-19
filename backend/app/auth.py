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
#
# Supabase now issues asymmetrically-signed tokens (ES256) and publishes
# the public keys at /auth/v1/.well-known/jwks. We fetch + cache those and
# verify tokens against them — no shared secret needs to live on our
# servers.
#
# Legacy HS256 (shared secret) is supported as a fallback for projects
# that haven't migrated. Pass SUPABASE_JWT_SECRET only if you're on a
# legacy project; otherwise leave it unset.

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bfhmaswnkzoowfxrsfce.supabase.co").rstrip("/")
_JWKS_URL = f"{_SUPABASE_URL}/auth/v1/.well-known/jwks"

# PyJWKClient caches keys internally and refreshes on `kid` misses.
_jwks_client = jwt.PyJWKClient(_JWKS_URL, cache_keys=True, lifespan=300)


def _legacy_hs256_secret() -> str:
    return os.environ.get("SUPABASE_JWT_SECRET", "").strip()


def _decode_token(token: str) -> dict:
    """Verify a Supabase JWT and return the payload, or raise HTTPException.

    Tries asymmetric (ES256 via JWKS) first since that's what modern
    Supabase projects use. Falls back to HS256 with SUPABASE_JWT_SECRET
    if the token's header says `alg: HS256` (legacy projects).
    """
    # Peek at the header to see which algorithm was used
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Malformed token: {e}")

    alg = header.get("alg", "")

    if alg == "HS256":
        secret = _legacy_hs256_secret()
        if not secret:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Legacy HS256 JWT received but SUPABASE_JWT_SECRET not configured",
            )
        try:
            return jwt.decode(
                token, secret, algorithms=["HS256"], audience="authenticated"
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(401, f"Invalid token: {e}")

    # Modern asymmetric signing (ES256 / RS256 / EdDSA) — verify via JWKS.
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[alg] if alg else ["ES256", "RS256", "EdDSA"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWKClientError as e:
        raise HTTPException(401, f"JWKS error: {e}")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")


async def get_current_user_id(authorization: str | None = Header(None)) -> str:
    """FastAPI dependency — returns the Supabase user id from a verified JWT.

    The frontend sends a Supabase access token in the Authorization header.
    We verify its signature (against Supabase's published public keys for
    modern projects, or the shared HS256 secret for legacy ones) before
    trusting the `sub` claim as the user id.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = _decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Token missing sub claim")
    return str(user_id)
