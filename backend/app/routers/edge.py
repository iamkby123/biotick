"""
Trading edge endpoints.

Provides data that gives traders an informational advantage:
- Historical catalyst price impact analysis
- Short interest data
- Institutional ownership
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

import httpx
from app.database import get_db
from app.models.catalyst import Catalyst
from app.models.company import Company
from app.models.trial import Trial
from app.cache.memory_cache import cache
from app.config import BIOTECH_SIC_CODES

router = APIRouter(prefix="/api/edge", tags=["edge"])
_executor = ThreadPoolExecutor(max_workers=2)


@router.get("/catalyst-impact")
async def get_catalyst_impact_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze historical catalyst outcomes by phase and therapeutic area.
    Shows success rates and typical price moves to help predict future catalysts.
    """
    cached = cache.get("catalyst_impact_stats")
    if cached:
        return cached

    # Get completed trials with results by phase
    result = await db.execute(
        select(
            Trial.phase,
            Trial.therapeutic_area,
            Trial.overall_status,
            func.count().label("cnt"),
        )
        .where(
            Trial.phase.in_(["PHASE1", "PHASE2", "PHASE3"]),
            Trial.overall_status.in_(["COMPLETED", "TERMINATED", "WITHDRAWN"]),
            Trial.company_ticker.isnot(None),
        )
        .group_by(Trial.phase, Trial.therapeutic_area, Trial.overall_status)
    )
    rows = result.all()

    # Calculate success rates by phase
    phase_stats: dict = {}
    for phase, area, status, count in rows:
        if phase not in phase_stats:
            phase_stats[phase] = {"completed": 0, "failed": 0, "total": 0}
        if status == "COMPLETED":
            phase_stats[phase]["completed"] += count
        else:
            phase_stats[phase]["failed"] += count
        phase_stats[phase]["total"] += count

    # Calculate success rates
    phase_success = {}
    for phase, stats in phase_stats.items():
        if stats["total"] > 0:
            rate = stats["completed"] / stats["total"]
            phase_success[phase] = {
                "success_rate": round(rate * 100, 1),
                "completed": stats["completed"],
                "failed": stats["failed"],
                "total": stats["total"],
            }

    # Success rates by therapeutic area (for Phase 3 only — most relevant)
    area_stats: dict = {}
    for phase, area, status, count in rows:
        if phase != "PHASE3" or not area:
            continue
        if area not in area_stats:
            area_stats[area] = {"completed": 0, "failed": 0, "total": 0}
        if status == "COMPLETED":
            area_stats[area]["completed"] += count
        else:
            area_stats[area]["failed"] += count
        area_stats[area]["total"] += count

    area_success = {}
    for area, stats in area_stats.items():
        if stats["total"] >= 5:  # Only show areas with enough data
            rate = stats["completed"] / stats["total"]
            area_success[area] = {
                "success_rate": round(rate * 100, 1),
                "completed": stats["completed"],
                "failed": stats["failed"],
                "total": stats["total"],
            }

    # Sort by success rate
    area_success = dict(sorted(area_success.items(), key=lambda x: x[1]["success_rate"], reverse=True))

    # Industry benchmarks (well-known biotech stats)
    benchmarks = {
        "phase1_to_approval": "~10%",
        "phase2_to_approval": "~25%",
        "phase3_to_approval": "~55%",
        "avg_phase3_oncology_move_success": "+15-40%",
        "avg_phase3_oncology_move_failure": "-30-60%",
        "avg_phase3_rare_disease_success": "+20-50%",
        "avg_fda_approval_move": "+5-15%",
        "avg_fda_rejection_move": "-40-70%",
        "avg_days_phase3_to_fda": "365-730",
    }

    response = {
        "phase_success_rates": phase_success,
        "phase3_by_therapeutic_area": area_success,
        "industry_benchmarks": benchmarks,
        "data_note": "Success rates based on trial completion vs termination/withdrawal. Actual clinical success may differ.",
    }

    cache.set("catalyst_impact_stats", response, 3600)
    return response


@router.get("/short-interest/{ticker}")
async def get_short_interest(ticker: str):
    """
    Get short interest data from Finnhub.
    Shows short volume, days to cover, and short ratio.
    """
    import os
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {"error": "Finnhub API key not configured"}

    cache_key = f"short_interest:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()

    async with httpx.AsyncClient(timeout=10) as client:
        # Get short interest from Finnhub
        try:
            resp = await client.get(
                "https://finnhub.io/api/v1/stock/short-interest",
                params={"symbol": ticker.upper(), "token": api_key},
            )
            short_data = resp.json() if resp.status_code == 200 else []
        except Exception:
            short_data = []

        # Get institutional ownership
        try:
            resp2 = await client.get(
                "https://finnhub.io/api/v1/institutional-ownership",
                params={"symbol": ticker.upper(), "token": api_key},
            )
            inst_data = resp2.json() if resp2.status_code == 200 else {}
        except Exception:
            inst_data = {}

        # Get insider sentiment
        try:
            resp3 = await client.get(
                "https://finnhub.io/api/v1/stock/insider-sentiment",
                params={"symbol": ticker.upper(), "token": api_key, "from": "2025-01-01"},
            )
            sentiment_data = resp3.json() if resp3.status_code == 200 else {}
        except Exception:
            sentiment_data = {}

    # Parse short interest
    short_interest = []
    if isinstance(short_data, list):
        for entry in short_data[-6:]:  # Last 6 reports
            short_interest.append({
                "date": entry.get("settlementDate"),
                "short_interest": entry.get("shortInterest"),
                "avg_volume": entry.get("avgDailyVolume"),
                "days_to_cover": entry.get("daysToCover"),
            })

    # Parse institutional ownership
    ownership = []
    if isinstance(inst_data, dict) and "ownership" in inst_data:
        for holder in inst_data["ownership"][:10]:
            ownership.append({
                "name": holder.get("name"),
                "shares": holder.get("share"),
                "change": holder.get("change"),
                "filing_date": holder.get("filingDate"),
            })

    # Parse insider sentiment
    sentiment = []
    if isinstance(sentiment_data, dict) and "data" in sentiment_data:
        for s in sentiment_data["data"][-6:]:
            sentiment.append({
                "month": f"{s.get('year')}-{str(s.get('month',0)).zfill(2)}",
                "change": s.get("change"),
                "mspr": s.get("mspr"),  # Monthly share purchase ratio
            })

    result = {
        "ticker": ticker.upper(),
        "short_interest": short_interest,
        "institutional_ownership": ownership,
        "insider_sentiment": sentiment,
    }

    cache.set(cache_key, result, 1800)
    return result


@router.get("/top-shorted")
async def get_top_shorted(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get top shorted biotech stocks.
    Queries the top N biotechs by market cap, then fetches short interest from Finnhub.
    Returns list sorted by short interest ratio (most shorted first).
    """
    import os
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {"stocks": [], "error": "Finnhub API key not configured"}

    cache_key = f"top_shorted:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Get top biotech companies by market cap
    result = await db.execute(
        select(Company)
        .where(
            Company.sic_code.in_(BIOTECH_SIC_CODES),
            Company.market_cap.isnot(None),
        )
        .order_by(Company.market_cap.desc())
        .limit(limit)
    )
    companies = result.scalars().all()

    # Fetch short interest for each ticker, in parallel batches
    async def fetch_short(client: httpx.AsyncClient, company: Company) -> dict | None:
        try:
            resp = await client.get(
                "https://finnhub.io/api/v1/stock/short-interest",
                params={"symbol": company.ticker, "token": api_key},
                timeout=8,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, list) or not data:
                return None
            latest = data[-1]
            return {
                "ticker": company.ticker,
                "name": company.name,
                "price": company.price,
                "market_cap": company.market_cap,
                "short_interest": latest.get("shortInterest"),
                "avg_volume": latest.get("avgDailyVolume"),
                "days_to_cover": latest.get("daysToCover"),
                "settlement_date": latest.get("settlementDate"),
            }
        except Exception:
            return None

    stocks = []
    async with httpx.AsyncClient() as client:
        # Run in batches of 10 to avoid hammering the API
        batch_size = 10
        for i in range(0, len(companies), batch_size):
            batch = companies[i:i + batch_size]
            results = await asyncio.gather(*[fetch_short(client, c) for c in batch])
            stocks.extend([r for r in results if r is not None])

    # Sort by days_to_cover descending (most shorted first)
    stocks.sort(key=lambda s: s.get("days_to_cover") or 0, reverse=True)

    response = {"stocks": stocks, "total": len(stocks)}
    cache.set(cache_key, response, 3600)  # Cache 1 hour
    return response


@router.get("/movers")
async def get_top_movers(
    db: AsyncSession = Depends(get_db),
):
    """Get top biotech movers — biggest gainers and losers today."""
    cached = cache.get("top_movers")
    if cached:
        return cached

    # Top gainers
    result = await db.execute(
        select(Company)
        .where(
            Company.sic_code.in_(BIOTECH_SIC_CODES),
            Company.price_change_pct.isnot(None),
            Company.price.isnot(None),
        )
        .order_by(Company.price_change_pct.desc())
        .limit(10)
    )
    gainers = [
        {"ticker": c.ticker, "name": c.name, "price": c.price, "change": c.price_change_pct, "market_cap": c.market_cap}
        for c in result.scalars().all()
    ]

    # Top losers
    result = await db.execute(
        select(Company)
        .where(
            Company.sic_code.in_(BIOTECH_SIC_CODES),
            Company.price_change_pct.isnot(None),
            Company.price.isnot(None),
        )
        .order_by(Company.price_change_pct.asc())
        .limit(10)
    )
    losers = [
        {"ticker": c.ticker, "name": c.name, "price": c.price, "change": c.price_change_pct, "market_cap": c.market_cap}
        for c in result.scalars().all()
    ]

    response = {"gainers": gainers, "losers": losers}
    cache.set("top_movers", response, 300)
    return response
