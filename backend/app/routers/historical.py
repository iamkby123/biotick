"""Historical catalyst events with price impact data."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from math import ceil

from app.database import get_db
from app.models.catalyst import Catalyst
from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/historical", tags=["historical"])


@router.get("/catalysts")
async def get_historical_catalysts(
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    event_type: str | None = Query(None),
    company_ticker: str | None = Query(None),
    min_significance: int = Query(3),
    db: AsyncSession = Depends(get_db),
):
    """Get past catalyst events with company price data."""
    query = select(Catalyst).where(Catalyst.is_past == True)

    if event_type:
        query = query.where(Catalyst.event_type == event_type)
    if company_ticker:
        query = query.where(Catalyst.company_ticker == company_ticker.upper())
    if min_significance:
        query = query.where(Catalyst.significance_score >= min_significance)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Get catalysts with company price data
    query = query.order_by(Catalyst.expected_date.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    catalysts = result.scalars().all()

    # Enrich with company data
    items = []
    for c in catalysts:
        # Get company info
        company_result = await db.execute(
            text("SELECT name, price, price_change_pct, market_cap FROM companies WHERE ticker = :t"),
            {"t": c.company_ticker},
        )
        company = company_result.fetchone()

        items.append({
            "id": c.id,
            "ticker": c.company_ticker,
            "company_name": company[0] if company else None,
            "current_price": company[1] if company else None,
            "market_cap": company[3] if company else None,
            "drug_name": c.drug_name,
            "drug_id": c.drug_id,
            "event_type": c.event_type,
            "event_description": c.event_description,
            "catalyst_date": c.expected_date.isoformat() if c.expected_date else None,
            "date_precision": c.date_precision,
            "significance_score": c.significance_score,
            "confidence": c.confidence,
            "outcome": c.outcome,
            "source": c.source,
            "source_url": c.source_url,
        })

    return {
        "catalysts": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }
