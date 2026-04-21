"""Public news feed endpoints."""

from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.news import NewsItem

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
async def list_news(
    ticker: str | None = Query(None, description="Filter to stories mentioning this ticker"),
    source: str | None = Query(None, description="Filter to one source (e.g. 'STAT')"),
    search: str | None = Query(None, description="Keyword filter over title/summary"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List recent news items, newest first."""
    query = select(NewsItem)

    if ticker:
        # text[] contains-check via the @> array operator
        query = query.where(NewsItem.tickers.contains([ticker.upper()]))

    if source:
        query = query.where(NewsItem.source == source)

    if search:
        s = f"%{search}%"
        query = query.where(
            or_(NewsItem.title.ilike(s), NewsItem.summary.ilike(s))
        )

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            query.order_by(NewsItem.published_at.desc().nullslast())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "source": r.source,
                "title": r.title,
                "url": r.url,
                "summary": r.summary,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "tickers": r.tickers or [],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    """List the distinct sources in the news table + their latest timestamp."""
    rows = (
        await db.execute(
            select(NewsItem.source, func.max(NewsItem.published_at), func.count())
            .group_by(NewsItem.source)
            .order_by(NewsItem.source)
        )
    ).all()
    return {
        "sources": [
            {"source": r[0], "last_published": r[1].isoformat() if r[1] else None, "count": r[2]}
            for r in rows
        ]
    }
