"""Short-interest endpoints (daily short-sale volume from FINRA Reg SHO)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.short_interest import ShortInterest

router = APIRouter(prefix="/api/short-interest", tags=["short-interest"])


@router.get("/{ticker}")
async def get_short_interest(
    ticker: str,
    days: int = Query(30, ge=1, le=180, description="Trailing days to return"),
    db: AsyncSession = Depends(get_db),
):
    """Return daily short-sale metrics for a ticker over the last `days`.

    Aggregates across all Reg SHO tapes — sums short_volume and total_volume
    across venues per day and recomputes short_pct on the aggregate.
    """
    ticker = ticker.upper()
    cutoff = date.today() - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                ShortInterest.report_date,
                func.sum(ShortInterest.short_volume).label("short_volume"),
                func.sum(ShortInterest.total_volume).label("total_volume"),
            )
            .where(ShortInterest.ticker == ticker, ShortInterest.report_date >= cutoff)
            .group_by(ShortInterest.report_date)
            .order_by(ShortInterest.report_date.asc())
        )
    ).all()

    if not rows:
        return {"ticker": ticker, "days": days, "items": [], "summary": None}

    items = []
    for r in rows:
        short = float(r.short_volume or 0)
        total = float(r.total_volume or 0)
        pct = (short / total) if total > 0 else None
        items.append(
            {
                "date": r.report_date.isoformat(),
                "short_volume": short,
                "total_volume": total,
                "short_pct": pct,
            }
        )

    # Summary: latest day + rolling averages for a compact card in the UI.
    latest = items[-1]
    avg_5 = sum(i["short_pct"] or 0 for i in items[-5:]) / max(1, min(5, len(items)))
    avg_20 = sum(i["short_pct"] or 0 for i in items[-20:]) / max(1, min(20, len(items)))

    return {
        "ticker": ticker,
        "days": days,
        "items": items,
        "summary": {
            "latest_date": latest["date"],
            "latest_short_pct": latest["short_pct"],
            "avg_5d_short_pct": avg_5,
            "avg_20d_short_pct": avg_20,
        },
    }
