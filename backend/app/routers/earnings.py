"""Biotech earnings calendar from Finnhub."""

import logging
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Query

from app.cache.memory_cache import cache
from app.config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/earnings", tags=["earnings"])


@router.get("")
async def get_earnings_calendar(
    start: str | None = Query(None, description="Start date YYYY-MM-DD"),
    end: str | None = Query(None, description="End date YYYY-MM-DD"),
):
    """Get upcoming biotech earnings dates from Finnhub."""
    today = date.today()
    start_date = start or today.isoformat()
    end_date = end or (today + timedelta(days=14)).isoformat()

    cache_key = f"earnings:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Get earnings calendar from Finnhub
            resp = await client.get("https://finnhub.io/api/v1/calendar/earnings", params={
                "from": start_date,
                "to": end_date,
                "token": FINNHUB_API_KEY,
            })
            if resp.status_code != 200:
                return {"earnings": [], "total": 0}

            data = resp.json()
            all_earnings = data.get("earningsCalendar", [])

            # Filter to biotech companies we track
            # Get our ticker set from DB
            from app.database import async_session
            from sqlalchemy import text
            async with async_session() as db:
                result = await db.execute(
                    text("SELECT ticker, name, price, market_cap FROM companies WHERE sic_code IS NOT NULL")
                )
                our_companies = {r[0]: {"name": r[1], "price": r[2], "market_cap": r[3]} for r in result.fetchall()}

            # Match and enrich
            biotech_earnings = []
            for e in all_earnings:
                sym = e.get("symbol", "")
                if sym in our_companies:
                    info = our_companies[sym]
                    biotech_earnings.append({
                        "ticker": sym,
                        "name": info["name"],
                        "date": e.get("date"),
                        "hour": e.get("hour", ""),  # bmo=before market, amc=after market
                        "eps_estimate": e.get("epsEstimate"),
                        "eps_actual": e.get("epsActual"),
                        "revenue_estimate": e.get("revenueEstimate"),
                        "revenue_actual": e.get("revenueActual"),
                        "price": info["price"],
                        "market_cap": info["market_cap"],
                    })

            # Sort by date
            biotech_earnings.sort(key=lambda x: x["date"] or "")

            result = {
                "earnings": biotech_earnings,
                "total": len(biotech_earnings),
                "date_range": {"start": start_date, "end": end_date},
            }
            cache.set(cache_key, result, 1800)
            return result

    except Exception as e:
        logger.error(f"Earnings calendar error: {e}")
        return {"earnings": [], "total": 0}
