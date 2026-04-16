import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
from fastapi import APIRouter, HTTPException

from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/options", tags=["options"])
_executor = ThreadPoolExecutor(max_workers=2)


def _make_session():
    """Create a requests session with browser-like headers."""
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    })
    return s

_yf_session = _make_session()


def _get_expirations(ticker: str) -> list[str]:
    """Get available option expiration dates (blocking)."""
    import time
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker, session=_yf_session)
            return list(t.options) if t.options else []
        except Exception as e:
            if "Rate" in str(e) or "429" in str(e):
                time.sleep(2 * (attempt + 1))
                continue
            raise
    return []


def _get_chain(ticker: str, expiration: str) -> dict:
    """Get options chain for a specific expiration (blocking)."""
    t = yf.Ticker(ticker, session=_yf_session)
    chain = t.option_chain(expiration)

    calls = []
    for _, row in chain.calls.iterrows():
        calls.append({
            "strike": float(row.get("strike", 0)),
            "bid": float(row.get("bid", 0)),
            "ask": float(row.get("ask", 0)),
            "last": float(row.get("lastPrice", 0)),
            "volume": int(row.get("volume", 0)) if row.get("volume") and row.get("volume") == row.get("volume") else 0,
            "open_interest": int(row.get("openInterest", 0)) if row.get("openInterest") and row.get("openInterest") == row.get("openInterest") else 0,
            "iv": round(float(row.get("impliedVolatility", 0)) * 100, 1),
            "in_the_money": bool(row.get("inTheMoney", False)),
        })

    puts = []
    for _, row in chain.puts.iterrows():
        puts.append({
            "strike": float(row.get("strike", 0)),
            "bid": float(row.get("bid", 0)),
            "ask": float(row.get("ask", 0)),
            "last": float(row.get("lastPrice", 0)),
            "volume": int(row.get("volume", 0)) if row.get("volume") and row.get("volume") == row.get("volume") else 0,
            "open_interest": int(row.get("openInterest", 0)) if row.get("openInterest") and row.get("openInterest") == row.get("openInterest") else 0,
            "iv": round(float(row.get("impliedVolatility", 0)) * 100, 1),
            "in_the_money": bool(row.get("inTheMoney", False)),
        })

    return {"calls": calls, "puts": puts, "expiration": expiration}


@router.get("/{ticker}/expirations")
async def get_expirations(ticker: str):
    """Get available option expiration dates."""
    cache_key = f"options_exp:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        expirations = await loop.run_in_executor(_executor, _get_expirations, ticker.upper())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get expirations: {e}")

    result = {"ticker": ticker.upper(), "expirations": expirations}
    cache.set(cache_key, result, 900)  # Cache 15 min to avoid rate limits
    return result


@router.get("/{ticker}/chain")
async def get_chain(ticker: str, expiration: str):
    """Get options chain for a specific expiration date."""
    cache_key = f"options_chain:{ticker}:{expiration}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        chain = await loop.run_in_executor(_executor, _get_chain, ticker.upper(), expiration)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get chain: {e}")

    chain["ticker"] = ticker.upper()
    cache.set(cache_key, chain, 600)  # Cache 10 min to avoid rate limits
    return chain
