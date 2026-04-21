"""ETF flow endpoints — daily shares-outstanding / AUM deltas."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.etf_flow import ETFFlowDaily

router = APIRouter(prefix="/api/etf-flows", tags=["etf-flows"])


@router.get("/{etf_ticker}")
async def get_etf_flows(
    etf_ticker: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Return daily snapshots for one ETF over the last N days."""
    etf_ticker = etf_ticker.upper()
    cutoff = date.today() - timedelta(days=days)

    rows = (
        await db.execute(
            select(ETFFlowDaily)
            .where(
                ETFFlowDaily.etf_ticker == etf_ticker,
                ETFFlowDaily.date >= cutoff,
            )
            .order_by(ETFFlowDaily.date.asc())
        )
    ).scalars().all()

    return {
        "etf_ticker": etf_ticker,
        "days": days,
        "series": [
            {
                "date": r.date.isoformat(),
                "shares_outstanding": float(r.shares_outstanding) if r.shares_outstanding is not None else None,
                "aum": float(r.aum) if r.aum is not None else None,
                "nav": float(r.nav) if r.nav is not None else None,
                "delta_shares": float(r.delta_shares) if r.delta_shares is not None else None,
                "delta_aum": float(r.delta_aum) if r.delta_aum is not None else None,
            }
            for r in rows
        ],
    }


@router.get("")
async def list_etf_flows(
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
):
    """Summary endpoint: latest snapshot + net flow over the window for
    every tracked ETF."""
    cutoff = date.today() - timedelta(days=days)

    rows = (
        await db.execute(
            select(ETFFlowDaily)
            .where(ETFFlowDaily.date >= cutoff)
            .order_by(ETFFlowDaily.etf_ticker, ETFFlowDaily.date.asc())
        )
    ).scalars().all()

    # Group by etf_ticker
    by_etf: dict[str, list[ETFFlowDaily]] = {}
    for r in rows:
        by_etf.setdefault(r.etf_ticker, []).append(r)

    etfs = []
    for etf, items in by_etf.items():
        if not items:
            continue
        latest = items[-1]
        net_shares = sum(
            float(i.delta_shares or 0) for i in items if i.delta_shares is not None
        )
        net_aum = sum(float(i.delta_aum or 0) for i in items if i.delta_aum is not None)
        etfs.append(
            {
                "etf_ticker": etf,
                "latest_date": latest.date.isoformat(),
                "shares_outstanding": float(latest.shares_outstanding)
                if latest.shares_outstanding is not None
                else None,
                "aum": float(latest.aum) if latest.aum is not None else None,
                "net_share_change": net_shares,
                "net_aum_change": net_aum,
            }
        )

    return {"days": days, "etfs": etfs}
