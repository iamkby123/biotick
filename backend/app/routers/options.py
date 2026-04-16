import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException

from app.cache.memory_cache import cache
from app.config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/options", tags=["options"])

YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


async def _fetch_yahoo_options(ticker: str, expiration_ts: int | None = None) -> dict:
    """Fetch options data from Yahoo Finance v7 API (no library, direct HTTP)."""
    url = f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}"
    params = {}
    if expiration_ts:
        params["date"] = str(expiration_ts)

    async with httpx.AsyncClient(headers=YAHOO_HEADERS, timeout=15) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return {}
        return resp.json()


@router.get("/{ticker}/expirations")
async def get_expirations(ticker: str):
    """Get available option expiration dates."""
    ticker = ticker.upper()
    cache_key = f"options_exp:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        data = await _fetch_yahoo_options(ticker)
        result_data = data.get("optionChain", {}).get("result", [])
        if not result_data:
            return {"ticker": ticker, "expirations": []}

        timestamps = result_data[0].get("expirationDates", [])
        expirations = [
            datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            for ts in timestamps
        ]

        result = {"ticker": ticker, "expirations": expirations}
        cache.set(cache_key, result, 900)
        return result
    except Exception as e:
        logger.warning(f"Options expirations error for {ticker}: {e}")
        return {"ticker": ticker, "expirations": []}


@router.get("/{ticker}/chain")
async def get_chain(ticker: str, expiration: str):
    """Get options chain for a specific expiration date."""
    ticker = ticker.upper()
    cache_key = f"options_chain:{ticker}:{expiration}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        # Convert date to Unix timestamp
        exp_dt = datetime.strptime(expiration, "%Y-%m-%d")
        exp_ts = int(exp_dt.timestamp())

        data = await _fetch_yahoo_options(ticker, exp_ts)
        result_data = data.get("optionChain", {}).get("result", [])
        if not result_data:
            return {"ticker": ticker, "calls": [], "puts": [], "expiration": expiration}

        options = result_data[0].get("options", [{}])[0]

        def parse_row(row: dict) -> dict:
            return {
                "strike": row.get("strike", 0),
                "bid": row.get("bid", 0),
                "ask": row.get("ask", 0),
                "last": row.get("lastPrice", 0),
                "volume": row.get("volume", 0),
                "open_interest": row.get("openInterest", 0),
                "iv": round(row.get("impliedVolatility", 0) * 100, 1),
                "in_the_money": row.get("inTheMoney", False),
            }

        calls = [parse_row(r) for r in options.get("calls", [])]
        puts = [parse_row(r) for r in options.get("puts", [])]

        chain = {"ticker": ticker, "calls": calls, "puts": puts, "expiration": expiration}
        cache.set(cache_key, chain, 600)
        return chain
    except Exception as e:
        logger.warning(f"Options chain error for {ticker}/{expiration}: {e}")
        return {"ticker": ticker, "calls": [], "puts": [], "expiration": expiration}
