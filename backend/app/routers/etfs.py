"""
ETF membership endpoints — which biotech ETFs include a given ticker and at what weight.

Powered by the `etf_holdings` table populated by `backend/scripts/sync_etf_holdings.py`.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.etf import ETFHolding
from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/companies", tags=["etfs"])


@router.get("/{ticker}/etfs")
async def get_etf_memberships(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """List ETFs that hold the given ticker, sorted by weight descending."""
    ticker = ticker.upper()
    cache_key = f"etfs:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(ETFHolding)
        .where(ETFHolding.ticker == ticker)
        .order_by(ETFHolding.weight.desc().nullslast())
    )
    rows = result.scalars().all()

    holdings = [
        {
            "id": h.id,
            "etf_ticker": h.etf_ticker,
            "ticker": h.ticker,
            "weight": h.weight,
            "shares": h.shares,
            "market_value": h.market_value,
            "updated_at": h.updated_at.isoformat() if h.updated_at else None,
        }
        for h in rows
    ]

    response = {
        "ticker": ticker,
        "etfs": holdings,
        "total": len(holdings),
    }
    cache.set(cache_key, response, 1800)  # 30 min
    return response
