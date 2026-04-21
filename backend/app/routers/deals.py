"""M&A / partnership / officer-change deal feed."""

from datetime import date, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.eight_k import Deal

router = APIRouter(prefix="/api/deals", tags=["deals"])


@router.get("")
async def list_deals(
    ticker: str | None = Query(None),
    deal_type: str | None = Query(None, description="material_agreement|acquisition|officer_change"),
    days: int = Query(90, ge=1, le=365),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=days)
    query = select(Deal).where(Deal.filed_date >= cutoff)
    if ticker:
        query = query.where(Deal.ticker == ticker.upper())
    if deal_type:
        query = query.where(Deal.deal_type == deal_type)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            query.order_by(Deal.filed_date.desc().nullslast(), Deal.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "ticker": r.ticker,
                "deal_type": r.deal_type,
                "counterparty": r.counterparty,
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
