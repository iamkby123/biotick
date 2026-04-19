"""Per-IP rate limiting for the public API.

Uses slowapi (FastAPI port of Flask-Limiter). In-memory storage is fine
here because we run a single Fly machine. If we scale horizontally we'd
swap in Redis.

Key notes:
- Fly terminates TLS and sets `fly-client-ip`; without it `request.client.host`
  is the internal proxy and every user would share one rate bucket.
- Most endpoints get a generous per-IP default.
- Expensive endpoints (Stripe checkout, any Anthropic-backed route) get
  stricter custom limits applied at the decorator level.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse


def _client_ip(request: Request) -> str:
    # Fly sets fly-client-ip with the real client address.
    fly = request.headers.get("fly-client-ip")
    if fly:
        return fly
    # Standard proxy header, take the first (client) entry.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


# 120 req/min = 2 req/sec per IP. Plenty of headroom for real users
# clicking around; blocks basic scrapers. Tighter limits on expensive
# endpoints are applied via @limiter.limit at the route level.
limiter = Limiter(
    key_func=_client_ip,
    default_limits=["120/minute"],
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a clean JSON 429 with Retry-After instead of slowapi's HTML default."""
    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "detail": f"Rate limit exceeded: {exc.detail}",
            "retry_after_seconds": int(getattr(exc, "reset_at", 60)) if hasattr(exc, "reset_at") else 60,
        },
    )
    return response
