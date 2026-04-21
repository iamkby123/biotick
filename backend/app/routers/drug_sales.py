"""Per-drug revenue endpoints (extracted from 10-Ks)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.adcom import DrugSales

router = APIRouter(prefix="/api/drug-sales", tags=["drug-sales"])


@router.get("/{ticker}")
async def get_drug_sales(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Return per-drug revenue by fiscal year for a ticker."""
    ticker = ticker.upper()
    rows = (
        await db.execute(
            select(DrugSales)
            .where(DrugSales.ticker == ticker)
            .order_by(DrugSales.fiscal_year.desc(), DrugSales.revenue_usd.desc())
        )
    ).scalars().all()

    return {
        "ticker": ticker,
        "items": [
            {
                "drug_name": r.drug_name,
                "fiscal_year": r.fiscal_year,
                "revenue_usd": float(r.revenue_usd) if r.revenue_usd is not None else None,
                "source_accession": r.source_accession,
            }
            for r in rows
        ],
    }


@router.get("")
async def list_top_drugs(
    fiscal_year: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Global leaderboard of top-selling drugs across the universe."""
    query = select(DrugSales)
    if fiscal_year:
        query = query.where(DrugSales.fiscal_year == fiscal_year)
    query = query.order_by(DrugSales.revenue_usd.desc().nullslast()).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    return {
        "items": [
            {
                "ticker": r.ticker,
                "drug_name": r.drug_name,
                "fiscal_year": r.fiscal_year,
                "revenue_usd": float(r.revenue_usd) if r.revenue_usd is not None else None,
            }
            for r in rows
        ]
    }
