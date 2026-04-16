import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
from fastapi import APIRouter

from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/options", tags=["options"])
_executor = ThreadPoolExecutor(max_workers=2)


def _get_expirations(ticker: str) -> list[str]:
    """Get available option expiration dates via yfinance (blocking)."""
    try:
        t = yf.Ticker(ticker)
        return list(t.options) if t.options else []
    except Exception as e:
        logger.warning(f"yfinance expirations error for {ticker}: {e}")
        return []


def _get_chain(ticker: str, expiration: str) -> dict:
    """Get options chain for a specific expiration via yfinance (blocking)."""
    t = yf.Ticker(ticker)
    chain = t.option_chain(expiration)

    def safe_int(v):
        try:
            if v != v:  # NaN check
                return 0
            return int(v)
        except (ValueError, TypeError):
            return 0

    def safe_float(v):
        try:
            if v != v:
                return 0.0
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    calls = [
        {
            "strike": safe_float(row.get("strike")),
            "bid": safe_float(row.get("bid")),
            "ask": safe_float(row.get("ask")),
            "last": safe_float(row.get("lastPrice")),
            "volume": safe_int(row.get("volume")),
            "open_interest": safe_int(row.get("openInterest")),
            "iv": round(safe_float(row.get("impliedVolatility")) * 100, 1),
            "in_the_money": bool(row.get("inTheMoney", False)),
        }
        for _, row in chain.calls.iterrows()
    ]

    puts = [
        {
            "strike": safe_float(row.get("strike")),
            "bid": safe_float(row.get("bid")),
            "ask": safe_float(row.get("ask")),
            "last": safe_float(row.get("lastPrice")),
            "volume": safe_int(row.get("volume")),
            "open_interest": safe_int(row.get("openInterest")),
            "iv": round(safe_float(row.get("impliedVolatility")) * 100, 1),
            "in_the_money": bool(row.get("inTheMoney", False)),
        }
        for _, row in chain.puts.iterrows()
    ]

    return {"calls": calls, "puts": puts, "expiration": expiration}


@router.get("/{ticker}/expirations")
async def get_expirations(ticker: str):
    """Get available option expiration dates."""
    ticker = ticker.upper()
    cache_key = f"options_exp:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    expirations = await asyncio.get_event_loop().run_in_executor(
        _executor, _get_expirations, ticker
    )
    result = {"ticker": ticker, "expirations": expirations}
    cache.set(cache_key, result, 900)
    return result


@router.get("/{ticker}/chain")
async def get_chain(ticker: str, expiration: str):
    """Get options chain for a specific expiration date."""
    ticker = ticker.upper()
    cache_key = f"options_chain:{ticker}:{expiration}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        chain = await asyncio.get_event_loop().run_in_executor(
            _executor, _get_chain, ticker, expiration
        )
        chain["ticker"] = ticker
        cache.set(cache_key, chain, 600)
        return chain
    except Exception as e:
        logger.warning(f"Options chain error for {ticker}: {e}")
        return {"ticker": ticker, "calls": [], "puts": [], "expiration": expiration}
