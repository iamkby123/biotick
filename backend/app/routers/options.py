import logging
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.database import get_db
from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/options", tags=["options"])


@router.get("/{ticker}/expirations")
async def get_expirations(ticker: str, db: AsyncSession = Depends(get_db)):
    """Get available option expiration dates from cached data."""
    ticker = ticker.upper()
    cache_key = f"options_exp:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        text("SELECT expiration FROM options_expirations WHERE ticker = :t AND expiration >= :today ORDER BY expiration"),
        {"t": ticker, "today": date.today()},
    )
    expirations = [row[0].isoformat() for row in result.fetchall()]

    resp = {"ticker": ticker, "expirations": expirations}
    cache.set(cache_key, resp, 300)
    return resp


@router.get("/{ticker}/chain")
async def get_chain(ticker: str, expiration: str, db: AsyncSession = Depends(get_db)):
    """Get options chain for a specific expiration date from cached data."""
    ticker = ticker.upper()
    cache_key = f"options_chain:{ticker}:{expiration}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        text("""SELECT option_type, strike, bid, ask, last_price, volume,
                       open_interest, implied_volatility, in_the_money
                FROM options_cache
                WHERE ticker = :t AND expiration = :exp
                ORDER BY strike"""),
        {"t": ticker, "exp": expiration},
    )
    rows = result.fetchall()

    calls = []
    puts = []
    for r in rows:
        entry = {
            "strike": r[1],
            "bid": r[2] or 0,
            "ask": r[3] or 0,
            "last": r[4] or 0,
            "volume": r[5] or 0,
            "open_interest": r[6] or 0,
            "iv": round((r[7] or 0) * 100, 1),
            "in_the_money": r[8] or False,
        }
        if r[0] == "call":
            calls.append(entry)
        else:
            puts.append(entry)

    chain = {"ticker": ticker, "calls": calls, "puts": puts, "expiration": expiration}
    cache.set(cache_key, chain, 300)
    return chain
