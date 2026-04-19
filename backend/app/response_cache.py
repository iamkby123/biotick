"""Simple in-memory response cache for hot read endpoints.

Why not Redis / external cache: single Fly machine, tiny working set
(hundreds of endpoints × query combinations), and we're explicitly
optimizing for cost. A process-local dict is the right tool.

Caching rules are prefix-based (see CACHE_RULES). GET-only, and only
status 200 JSON responses are cached. If a request carries an
Authorization header we skip the cache — auth'd responses may contain
per-user data.
"""

from __future__ import annotations

import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Prefix -> TTL in seconds. More specific prefixes should come first.
# Keep these conservative — we'd rather serve slightly-stale than wrong.
CACHE_RULES: list[tuple[str, int]] = [
    # Very stable data
    ("/api/conferences",         600),  # 10 min
    ("/api/etfs",                600),
    ("/api/institutional",       600),
    ("/api/patents",             600),
    # Updates every few hours at most
    ("/api/pdufa",               300),  # 5 min
    ("/api/earnings",            300),
    ("/api/predictions/trial",   300),
    ("/api/predictions/batch",   180),
    # Updates more often
    ("/api/historical",          120),  # 2 min
    ("/api/drugs",               120),
    ("/api/companies",            60),  # 1 min — prices tick
    ("/api/catalysts",            60),
    ("/api/trials",              120),
    ("/api/competitors",         300),
    # Health + misc
    ("/api/health",               10),  # short — mainly smooths load tests
]

# Cap to avoid unbounded memory growth on a 512MB machine.
_MAX_ENTRIES = 800

# key -> (expires_at, status_code, body_bytes, headers_dict)
# Storing the full headers dict (minus hop-by-hop) so we don't strip
# anything the route set intentionally.
_CACHE: dict[str, tuple[float, int, bytes, dict[str, str]]] = {}

# Headers that describe the wire representation rather than the payload.
# Critical: content-encoding must NOT be cached. The cache sits *inside*
# gzip in the middleware stack, so stored bodies are always uncompressed;
# gzip middleware re-applies compression on egress per client.
_HOP_HEADERS = {
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}


def _ttl_for(path: str) -> int:
    for prefix, ttl in CACHE_RULES:
        if path.startswith(prefix):
            return ttl
    return 0


def _evict_expired_locked(now: float) -> None:
    """Drop expired entries. Called opportunistically on writes."""
    dead = [k for k, v in _CACHE.items() if v[0] <= now]
    for k in dead:
        _CACHE.pop(k, None)


def _evict_oldest_locked(target: int) -> None:
    """Drop the n entries closest to expiry. Used when over _MAX_ENTRIES."""
    if len(_CACHE) <= target:
        return
    # Sort by expires_at ascending; drop the first few
    ordered = sorted(_CACHE.items(), key=lambda kv: kv[1][0])
    for k, _ in ordered[: len(_CACHE) - target]:
        _CACHE.pop(k, None)


def cache_stats() -> dict:
    """Expose for /api/health to help verify the cache is working in prod."""
    now = time.time()
    fresh = sum(1 for v in _CACHE.values() if v[0] > now)
    return {"entries": len(_CACHE), "fresh": fresh}


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """Cache 200 responses for configured GET routes."""

    async def dispatch(self, request: Request, call_next):
        if request.method != "GET":
            return await call_next(request)

        path = request.url.path
        ttl = _ttl_for(path)
        if ttl == 0:
            return await call_next(request)

        # Auth'd requests may contain per-user content.
        if request.headers.get("authorization"):
            return await call_next(request)

        key = f"{path}?{request.url.query}"
        now = time.time()
        hit = _CACHE.get(key)
        if hit and hit[0] > now:
            expires_at, status, body, saved_headers = hit
            age = int(ttl - (expires_at - now))
            headers = dict(saved_headers)
            headers["x-cache"] = "HIT"
            headers["age"] = str(max(0, age))
            headers["cache-control"] = f"public, max-age={int(expires_at - now)}"
            return Response(content=body, status_code=status, headers=headers)

        response = await call_next(request)

        # Only cache successful JSON responses.
        if response.status_code != 200:
            return response
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # BaseHTTPMiddleware gives us a streaming response; consume the body
        # fully so we can store it + re-serve it.
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Preserve route-set headers, dropping hop-by-hop ones (especially
        # content-encoding, which must be re-applied by gzip per client).
        saved_headers = {
            k: v for k, v in response.headers.items() if k.lower() not in _HOP_HEADERS
        }

        # Skip huge payloads (>256KB) — keep the cache dense on 512MB.
        if len(body) <= 262_144:
            _CACHE[key] = (now + ttl, response.status_code, body, saved_headers)
            if len(_CACHE) > _MAX_ENTRIES:
                _evict_expired_locked(now)
                _evict_oldest_locked(_MAX_ENTRIES)

        response_headers = dict(saved_headers)
        response_headers["x-cache"] = "MISS"
        response_headers["cache-control"] = f"public, max-age={ttl}"
        return Response(
            content=body,
            status_code=response.status_code,
            headers=response_headers,
        )
