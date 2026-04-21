"""Congressional trades endpoint (House only for now)."""

from datetime import date, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.adcom import CongressTrade

router = APIRouter(prefix="/api/congress-trades", tags=["congress-trades"])


@router.get("")
async def list_congress_trades(
    ticker: str | None = Query(None),
    trade_type: str | None = Query(None),
    days: int = Query(365, ge=1, le=730),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=days)
    query = select(CongressTrade).where(CongressTrade.trade_date >= cutoff)
    if ticker:
        query = query.where(CongressTrade.ticker == ticker.upper())
    if trade_type:
        query = query.where(CongressTrade.trade_type == trade_type)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            query.order_by(CongressTrade.trade_date.desc().nullslast(), CongressTrade.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "chamber": r.chamber,
                "member_name": r.member_name,
                "party": r.party,
                "state": r.state,
                "ticker": r.ticker,
                "trade_type": r.trade_type,
                "trade_date": r.trade_date.isoformat() if r.trade_date else None,
                "filing_date": r.filing_date.isoformat() if r.filing_date else None,
                "amount_min": float(r.amount_min) if r.amount_min else None,
                "amount_max": float(r.amount_max) if r.amount_max else None,
                "disclosure_url": r.disclosure_url,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }
