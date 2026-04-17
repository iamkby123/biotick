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


@router.get("/{ticker}/volume-summary")
async def get_volume_summary(ticker: str, db: AsyncSession = Depends(get_db)):
    """Get call vs put volume by expiration date for charting."""
    ticker = ticker.upper()
    cache_key = f"options_vol:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        text("""SELECT expiration, option_type, SUM(volume) as total_volume, SUM(open_interest) as total_oi,
                       AVG(CASE WHEN implied_volatility > 0 AND implied_volatility < 5 THEN implied_volatility END) as avg_iv
                FROM options_cache
                WHERE ticker = :t
                GROUP BY expiration, option_type
                ORDER BY expiration"""),
        {"t": ticker},
    )
    rows = result.fetchall()

    # Group by expiration
    by_exp: dict = {}
    for exp, opt_type, vol, oi, iv in rows:
        key = exp.isoformat()
        if key not in by_exp:
            by_exp[key] = {"expiration": key, "call_volume": 0, "put_volume": 0, "call_oi": 0, "put_oi": 0, "call_iv": 0, "put_iv": 0, "avg_iv": 0}
        if opt_type == "call":
            by_exp[key]["call_volume"] = vol or 0
            by_exp[key]["call_oi"] = oi or 0
            by_exp[key]["call_iv"] = round((iv or 0) * 100, 1)
        else:
            by_exp[key]["put_volume"] = vol or 0
            by_exp[key]["put_oi"] = oi or 0
            by_exp[key]["put_iv"] = round((iv or 0) * 100, 1)

    # Compute average IV across calls+puts per expiration
    for key in by_exp:
        d = by_exp[key]
        ivs = [v for v in [d["call_iv"], d["put_iv"]] if v > 0]
        d["avg_iv"] = round(sum(ivs) / len(ivs), 1) if ivs else 0

    data = list(by_exp.values())

    # Calculate put/call ratio
    total_call_vol = sum(d["call_volume"] for d in data)
    total_put_vol = sum(d["put_volume"] for d in data)
    pc_ratio = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

    # Overall avg IV
    overall_ivs = [d["avg_iv"] for d in data if d["avg_iv"] > 0]
    overall_iv = round(sum(overall_ivs) / len(overall_ivs), 1) if overall_ivs else 0

    resp = {
        "ticker": ticker,
        "data": data,
        "total_call_volume": total_call_vol,
        "total_put_volume": total_put_vol,
        "put_call_ratio": pc_ratio,
        "avg_iv": overall_iv,
    }
    cache.set(cache_key, resp, 300)
    return resp
