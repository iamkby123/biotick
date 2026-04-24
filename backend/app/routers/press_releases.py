"""Press-release feed endpoints."""

from datetime import date, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.eight_k import PressRelease

router = APIRouter(prefix="/api/press-releases", tags=["press-releases"])


@router.get("")
async def list_press_releases(
    ticker: str | None = Query(None),
    days: int = Query(60, ge=1, le=365, description="Lookback window in days"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=days)
    query = select(PressRelease).where(PressRelease.filed_date >= cutoff)
    if ticker:
        query = query.where(PressRelease.ticker == ticker.upper())

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            query.order_by(PressRelease.filed_date.desc().nullslast(), PressRelease.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "ticker": r.ticker,
                "headline": r.headline,
                "summary": r.summary,
                "url": r.url,
                "item_code": r.item_code,
                "filed_date": r.filed_date.isoformat() if r.filed_date else None,
                "accession_number": r.accession_number,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }
