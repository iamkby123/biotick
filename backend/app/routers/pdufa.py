"""PDUFA calendar and conference schedule API."""

from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from math import ceil

from app.database import get_db
from app.models.catalyst import Catalyst
from app.models.conference import Conference
from app.cache.memory_cache import cache

router = APIRouter(prefix="/api", tags=["pdufa", "conferences"])


# ── PDUFA Calendar ──────────────────────────────────────────────────

@router.get("/pdufa")
async def get_pdufa_dates(
    upcoming_only: bool = Query(True),
    months_ahead: int = Query(12, ge=1, le=36),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get PDUFA target action dates (FDA approval decision deadlines)."""
    today = date.today()

    query = select(Catalyst).where(
        Catalyst.event_type.in_(["PDUFA", "FDA_APPROVAL", "ADVISORY_COMMITTEE"])
    )

    if upcoming_only:
        query = query.where(Catalyst.expected_date >= today)
        query = query.where(
            Catalyst.expected_date <= today + timedelta(days=months_ahead * 30)
        )

    # Count
    from sqlalchemy import func
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Catalyst.expected_date.asc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": e.id,
                "company_ticker": e.company_ticker,
                "drug_name": e.drug_name,
                "event_type": e.event_type,
                "event_description": e.event_description,
                "expected_date": e.expected_date.isoformat() if e.expected_date else None,
                "date_precision": e.date_precision,
                "significance_score": e.significance_score,
                "confidence": e.confidence,
                "source": e.source,
                "source_url": e.source_url,
                "is_past": e.is_past,
                "outcome": e.outcome,
            }
            for e in events
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


# ── Conference Schedule ─────────────────────────────────────────────

@router.get("/conferences")
async def list_conferences(
    upcoming_only: bool = Query(True),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List biotech/pharma conferences."""
    cache_key = f"conferences:{upcoming_only}:{category}:{page}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    today = date.today()
    query = select(Conference)

    if upcoming_only:
        query = query.where(Conference.end_date >= today)
    if category:
        query = query.where(Conference.category == category)

    from sqlalchemy import func
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Conference.start_date.asc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    conferences = result.scalars().all()

    response = {
        "conferences": [
            {
                "id": c.id,
                "name": c.name,
                "short_name": c.short_name,
                "organizer": c.organizer,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat(),
                "location": c.location,
                "city": c.city,
                "country": c.country,
                "description": c.description,
                "website": c.website,
                "category": c.category,
                "significance": c.significance,
                "is_virtual": c.is_virtual,
            }
            for c in conferences
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }

    cache.set(cache_key, response, 3600)
    return response


@router.get("/conferences/categories")
async def get_conference_categories(
    db: AsyncSession = Depends(get_db),
):
    """Get list of conference categories."""
    from sqlalchemy import func
    result = await db.execute(
        select(Conference.category, func.count())
        .group_by(Conference.category)
        .order_by(func.count().desc())
    )
    rows = result.all()
    return {"categories": [{"name": r[0], "count": r[1]} for r in rows if r[0]]}
