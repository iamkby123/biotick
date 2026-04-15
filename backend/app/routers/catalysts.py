from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from math import ceil

from app.database import get_db
from app.models.catalyst import Catalyst
from app.cache.memory_cache import cache
from app.config import CACHE_TTL_CATALYSTS

router = APIRouter(prefix="/api/catalysts", tags=["catalysts"])


@router.get("")
async def list_catalysts(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    company_ticker: str | None = Query(None),
    event_type: str | None = Query(None),
    min_significance: int | None = Query(None),
    confidence: str | None = Query(None),
    include_past: bool = Query(False),
    sort_by: str = Query("expected_date"),
    sort_dir: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List and filter catalysts."""
    query = select(Catalyst)

    # Default: only future catalysts
    if not include_past:
        query = query.where(Catalyst.is_past == False)

    if start_date:
        query = query.where(Catalyst.expected_date >= start_date)
    if end_date:
        query = query.where(Catalyst.expected_date <= end_date)
    if company_ticker:
        query = query.where(Catalyst.company_ticker == company_ticker.upper())
    if event_type:
        query = query.where(Catalyst.event_type == event_type)
    if min_significance is not None:
        query = query.where(Catalyst.significance_score >= min_significance)
    if confidence:
        query = query.where(Catalyst.confidence == confidence)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort
    sort_col = getattr(Catalyst, sort_by, Catalyst.expected_date)
    if sort_dir == "desc":
        query = query.order_by(sort_col.desc().nullslast())
    else:
        query = query.order_by(sort_col.asc().nullslast())

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    catalysts = result.scalars().all()

    return {
        "catalysts": [_serialize(c) for c in catalysts],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/upcoming")
async def get_upcoming_catalysts(
    days: int = Query(90, description="Number of days to look ahead"),
    min_significance: int = Query(5, description="Minimum significance score"),
    db: AsyncSession = Depends(get_db),
):
    """Get high-significance upcoming catalysts."""
    cache_key = f"upcoming_catalysts:{days}:{min_significance}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    today = date.today()
    end = today + timedelta(days=days)

    result = await db.execute(
        select(Catalyst)
        .where(
            and_(
                Catalyst.expected_date >= today,
                Catalyst.expected_date <= end,
                Catalyst.significance_score >= min_significance,
                Catalyst.is_past == False,
            )
        )
        .order_by(Catalyst.expected_date.asc())
        .limit(50)
    )
    catalysts = result.scalars().all()

    response = {
        "catalysts": [_serialize(c) for c in catalysts],
        "total": len(catalysts),
        "date_range": {"start": today.isoformat(), "end": end.isoformat()},
    }

    cache.set(cache_key, response, CACHE_TTL_CATALYSTS)
    return response


@router.get("/calendar")
async def get_calendar_data(
    year: int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get catalyst counts by day for calendar view."""
    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # Get first and last day of month
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    result = await db.execute(
        select(Catalyst)
        .where(
            and_(
                Catalyst.expected_date >= start,
                Catalyst.expected_date <= end,
            )
        )
        .order_by(Catalyst.expected_date.asc())
    )
    catalysts = result.scalars().all()

    # Group by day
    days: dict = {}
    for c in catalysts:
        day_key = c.expected_date.isoformat() if c.expected_date else None
        if day_key:
            if day_key not in days:
                days[day_key] = []
            days[day_key].append(_serialize(c))

    return {
        "year": year,
        "month": month,
        "days": days,
        "total_catalysts": len(catalysts),
    }


def _serialize(c: Catalyst) -> dict:
    return {
        "id": c.id,
        "company_ticker": c.company_ticker,
        "drug_id": c.drug_id,
        "drug_name": c.drug_name,
        "event_type": c.event_type,
        "event_description": c.event_description,
        "expected_date": c.expected_date.isoformat() if c.expected_date else None,
        "date_precision": c.date_precision,
        "significance_score": c.significance_score,
        "confidence": c.confidence,
        "source": c.source,
        "source_url": c.source_url,
        "is_past": c.is_past,
        "outcome": c.outcome,
    }
