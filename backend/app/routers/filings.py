from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from math import ceil

from app.database import get_db
from app.models.filing import SECFiling, InsiderTrade

router = APIRouter(prefix="/api", tags=["filings"])


@router.get("/companies/{ticker}/filings")
async def get_company_filings(
    ticker: str,
    filing_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get SEC filings for a company."""
    query = select(SECFiling).where(SECFiling.ticker == ticker.upper())

    if filing_type:
        query = query.where(SECFiling.filing_type == filing_type)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort and paginate
    query = query.order_by(SECFiling.filed_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    filings = result.scalars().all()

    return {
        "filings": [
            {
                "id": f.id,
                "ticker": f.ticker,
                "filing_type": f.filing_type,
                "filed_date": f.filed_date.isoformat() if f.filed_date else None,
                "edgar_url": f.edgar_url,
                "description": f.description,
                "accession_number": f.accession_number,
            }
            for f in filings
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/companies/{ticker}/insider-trades")
async def get_company_insider_trades(
    ticker: str,
    trade_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get insider trades for a company."""
    query = select(InsiderTrade).where(InsiderTrade.ticker == ticker.upper())

    if trade_type:
        query = query.where(InsiderTrade.trade_type == trade_type)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort and paginate
    query = query.order_by(InsiderTrade.transaction_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    trades = result.scalars().all()

    return {
        "trades": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "insider_name": t.insider_name,
                "insider_title": t.insider_title,
                "trade_type": t.trade_type,
                "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
                "shares": t.shares,
                "price_per_share": t.price_per_share,
                "total_value": t.total_value,
                "shares_owned_after": t.shares_owned_after,
                "filing_date": t.filing_date.isoformat() if t.filing_date else None,
                "is_direct": t.is_direct,
            }
            for t in trades
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/filings/insider-trades")
async def get_all_insider_trades(
    trade_type: str | None = Query(None),
    sort_by: str = Query("transaction_date"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get all insider trades across all biotech companies."""
    query = select(InsiderTrade)

    if trade_type:
        query = query.where(InsiderTrade.trade_type == trade_type)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(InsiderTrade, sort_by, InsiderTrade.transaction_date)
    if sort_dir == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    trades = result.scalars().all()

    return {
        "trades": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "insider_name": t.insider_name,
                "insider_title": t.insider_title,
                "trade_type": t.trade_type,
                "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
                "shares": t.shares,
                "price_per_share": t.price_per_share,
                "total_value": t.total_value,
                "filing_date": t.filing_date.isoformat() if t.filing_date else None,
            }
            for t in trades
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/companies/{ticker}/insider-summary")
async def get_insider_summary(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get insider trading summary — net buys vs sells in last 90 days."""
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=90)

    result = await db.execute(
        select(InsiderTrade).where(
            InsiderTrade.ticker == ticker.upper(),
            InsiderTrade.transaction_date >= cutoff,
            InsiderTrade.trade_type.in_(["PURCHASE", "SALE"]),
        )
    )
    trades = result.scalars().all()

    buys = sum(t.total_value or 0 for t in trades if t.trade_type == "PURCHASE")
    sells = sum(t.total_value or 0 for t in trades if t.trade_type == "SALE")
    buy_count = sum(1 for t in trades if t.trade_type == "PURCHASE")
    sell_count = sum(1 for t in trades if t.trade_type == "SALE")

    return {
        "period_days": 90,
        "total_buy_value": buys,
        "total_sell_value": sells,
        "net_value": buys - sells,
        "buy_transactions": buy_count,
        "sell_transactions": sell_count,
        "signal": "BULLISH" if buys > sells else "BEARISH" if sells > buys else "NEUTRAL",
    }
