"""FDA Advisory Committee meeting endpoints."""

from datetime import date, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.adcom import AdComMeeting

router = APIRouter(prefix="/api/adcom", tags=["adcom"])


@router.get("")
async def list_adcom(
    upcoming: bool = Query(True),
    ticker: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(AdComMeeting)
    if upcoming:
        query = query.where(AdComMeeting.meeting_date >= date.today() - timedelta(days=3))
    if ticker:
        query = query.where(AdComMeeting.company_ticker == ticker.upper())

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0

    order = AdComMeeting.meeting_date.asc() if upcoming else AdComMeeting.meeting_date.desc()
    rows = (
        await db.execute(
            query.order_by(order.nullslast()).offset((page - 1) * per_page).limit(per_page)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "committee": r.committee,
                "meeting_date": r.meeting_date.isoformat() if r.meeting_date else None,
                "topics": r.topics,
                "drug_name": r.drug_name,
                "company_ticker": r.company_ticker,
                "url": r.url,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }
