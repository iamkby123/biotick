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
async def get_short_interest(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get short-interest + institutional-ownership + insider-sentiment for
    a single ticker. Short interest comes from OUR `short_interest` table
    (populated nightly from FINRA Reg SHO CSVs — free, reliable). Finnhub's
    `/stock/short-interest` is paid-tier and returns 403 for us, so we
    don't touch it. Institutional ownership + insider sentiment are also
    paid-tier endpoints; we try them but quietly tolerate empty results.
    """
    import os
    from sqlalchemy import select, desc
    from app.models.short_interest import ShortInterest

    ticker = ticker.upper()
    api_key = os.environ.get("FINNHUB_API_KEY", "")

    cache_key = f"short_interest:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Short interest: use our local FINRA table (last 30 daily rows).
    # The table stores daily short_volume + total_volume + short_pct
    # (shares shorted / total traded that day). Traditional "days-to-
    # cover" isn't available because we don't have average daily volume
    # over a trailing window — we pass short_pct through as the metric.
    short_interest: list[dict] = []
    rows = (
        await db.execute(
            select(ShortInterest)
            .where(ShortInterest.ticker == ticker)
            .order_by(desc(ShortInterest.report_date))
            .limit(30)
        )
    ).scalars().all()
    for r in reversed(rows):
        short_interest.append({
            "date": r.report_date.isoformat() if r.report_date else None,
            "short_interest": float(r.short_volume) if r.short_volume is not None else None,
            "avg_volume": float(r.total_volume) if r.total_volume is not None else None,
            "days_to_cover": float(r.short_pct) if r.short_pct is not None else None,
        })

    # Institutional ownership + insider sentiment — paid tier, best effort.
    ownership: list[dict] = []
    sentiment: list[dict] = []
    if api_key:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp2 = await client.get(
                    "https://finnhub.io/api/v1/institutional-ownership",
                    params={"symbol": ticker, "token": api_key},
                )
                inst_data = resp2.json() if resp2.status_code == 200 else {}
                if isinstance(inst_data, dict) and "ownership" in inst_data:
                    for holder in inst_data["ownership"][:10]:
                        ownership.append({
                            "name": holder.get("name"),
                            "shares": holder.get("share"),
                            "change": holder.get("change"),
                            "filing_date": holder.get("filingDate"),
                        })
            except Exception:
                pass

            try:
                resp3 = await client.get(
                    "https://finnhub.io/api/v1/stock/insider-sentiment",
                    params={"symbol": ticker, "token": api_key, "from": "2025-01-01"},
                )
                sentiment_data = resp3.json() if resp3.status_code == 200 else {}
                if isinstance(sentiment_data, dict) and "data" in sentiment_data:
                    for s in sentiment_data["data"][-6:]:
                        sentiment.append({
                            "month": f"{s.get('year')}-{str(s.get('month',0)).zfill(2)}",
                            "change": s.get("change"),
                            "mspr": s.get("mspr"),
                        })
            except Exception:
                pass

    result = {
        "ticker": ticker,
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
    Top shorted biotech tickers by days-to-cover, from our local
    `short_interest` table (FINRA Reg SHO daily feed). For each ticker
    we pick the most recent settlement-date row and rank by days_to_cover
    descending. Joins `companies` for name / price / market_cap.

    Previously this hit Finnhub's paid /stock/short-interest endpoint
    and returned empty on free tier.
    """
    from sqlalchemy import select, desc
    from app.models.short_interest import ShortInterest

    cache_key = f"top_shorted:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Rank by average short_pct over the last 30 days per ticker so
    # one-off spikes don't dominate. Filter out warrant/unit/right
    # tickers (5-char symbols ending in W/U/R) — those trade thinly
    # and skew to 100% short_pct for meaningless reasons.
    sql = """
        WITH recent AS (
          SELECT si.ticker, AVG(si.short_pct) AS avg_short_pct,
                 MAX(si.report_date) AS latest_date,
                 AVG(si.short_volume) AS avg_short_vol,
                 AVG(si.total_volume) AS avg_total_vol,
                 SUM(si.total_volume) AS total_liquidity
          FROM short_interest si
          WHERE si.report_date >= (CURRENT_DATE - INTERVAL '30 days')
          GROUP BY si.ticker
        )
        SELECT r.ticker, r.latest_date, r.avg_short_vol, r.avg_total_vol,
               r.avg_short_pct, c.name, c.price, c.market_cap
        FROM recent r
        JOIN companies c ON c.ticker = r.ticker
        WHERE r.avg_short_pct IS NOT NULL
          AND c.sic_code = ANY(:sic_codes)
          AND LENGTH(r.ticker) <= 4
          AND r.total_liquidity > 100000
        ORDER BY r.avg_short_pct DESC NULLS LAST
        LIMIT :lim
    """
    from sqlalchemy import text as sa_text

    result = await db.execute(
        sa_text(sql),
        {"sic_codes": list(BIOTECH_SIC_CODES), "lim": limit},
    )
    stocks = [
        {
            "ticker": r[0],
            "settlement_date": r[1].isoformat() if r[1] else None,
            "short_interest": float(r[2]) if r[2] is not None else None,
            "avg_volume": float(r[3]) if r[3] is not None else None,
            "days_to_cover": float(r[4]) if r[4] is not None else None,  # actually short_pct
            "name": r[5],
            "price": float(r[6]) if r[6] is not None else None,
            "market_cap": float(r[7]) if r[7] is not None else None,
        }
        for r in result.fetchall()
    ]

    response = {"stocks": stocks, "total": len(stocks)}
    cache.set(cache_key, response, 3600)
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
