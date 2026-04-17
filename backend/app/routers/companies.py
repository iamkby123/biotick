import logging
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from math import ceil

from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyListItem, CompanyListResponse, CompanyDetail
from app.cache.memory_cache import cache
from app.config import CACHE_TTL_SCREENER, CACHE_TTL_COMPANY_DETAIL, BIOTECH_SIC_CODES, FINNHUB_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    search: str | None = Query(None, description="Search by ticker or company name"),
    exchange: str | None = Query(None),
    min_market_cap: float | None = Query(None),
    max_market_cap: float | None = Query(None),
    sector: str | None = Query(None),
    therapeutic_area: str | None = Query(None),
    # Biotech-specific filters
    max_runway_months: int | None = Query(None, description="Max runway (e.g. 6 for <6mo runway companies)"),
    min_runway_months: int | None = Query(None),
    highest_phase: str | None = Query(None, description="PHASE1, PHASE2, PHASE3, PHASE4"),
    profitability: str | None = Query(None, description="profitable | pre-revenue"),
    has_catalyst_days: int | None = Query(None, description="Has a catalyst in next N days"),
    sort_by: str = Query("market_cap", description="Sort field"),
    sort_dir: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List and search biotech companies with filtering and pagination."""
    # Build cache key from params
    cache_key = f"companies:{search}:{exchange}:{min_market_cap}:{max_market_cap}:{sector}:{therapeutic_area}:{max_runway_months}:{min_runway_months}:{highest_phase}:{profitability}:{has_catalyst_days}:{sort_by}:{sort_dir}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Base query - only biotech companies (have SIC code in biotech set)
    query = select(Company).where(Company.sic_code.in_(BIOTECH_SIC_CODES))

    # Filters
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Company.ticker.ilike(search_term),
                Company.name.ilike(search_term),
            )
        )

    if exchange:
        query = query.where(Company.exchange == exchange)

    if min_market_cap is not None:
        query = query.where(Company.market_cap >= min_market_cap)

    if max_market_cap is not None:
        query = query.where(Company.market_cap <= max_market_cap)

    if sector:
        query = query.where(Company.sector.ilike(f"%{sector}%"))

    if therapeutic_area:
        query = query.where(Company.therapeutic_area.ilike(f"%{therapeutic_area}%"))

    # Biotech filters
    if max_runway_months is not None:
        query = query.where(Company.runway_months.isnot(None))
        query = query.where(Company.runway_months <= max_runway_months)
    if min_runway_months is not None:
        query = query.where(Company.runway_months >= min_runway_months)

    if highest_phase:
        from app.models.drug import Drug
        subq = select(Drug.company_ticker).where(Drug.highest_phase == highest_phase).distinct()
        query = query.where(Company.ticker.in_(subq))

    if profitability == "profitable":
        query = query.where(Company.profit_margin > 0)
    elif profitability == "pre-revenue":
        query = query.where(or_(Company.revenue.is_(None), Company.revenue == 0))

    if has_catalyst_days:
        from app.models.catalyst import Catalyst
        cutoff = date.today() + timedelta(days=has_catalyst_days)
        today = date.today()
        subq = select(Catalyst.company_ticker).where(
            Catalyst.expected_date >= today,
            Catalyst.expected_date <= cutoff,
            Catalyst.is_past == False,
        ).distinct()
        query = query.where(Company.ticker.in_(subq))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sort
    sort_column = getattr(Company, sort_by, Company.market_cap)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc().nullslast())
    else:
        query = query.order_by(sort_column.desc().nullslast())

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    companies = result.scalars().all()

    response = CompanyListResponse(
        companies=[CompanyListItem.model_validate(c) for c in companies],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=ceil(total / per_page) if total > 0 else 0,
    )

    cache.set(cache_key, response, CACHE_TTL_SCREENER)
    return response


@router.get("/{ticker}", response_model=CompanyDetail)
async def get_company(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get full company detail."""
    cache_key = f"company:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(Company).where(Company.ticker == ticker.upper())
    )
    company = result.scalar_one_or_none()

    if not company:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    response = CompanyDetail.model_validate(company)
    cache.set(cache_key, response, CACHE_TTL_COMPANY_DETAIL)
    return response


@router.get("/meta/exchanges")
async def get_exchanges(db: AsyncSession = Depends(get_db)):
    """Get all unique exchanges."""
    result = await db.execute(
        select(Company.exchange).distinct().where(Company.exchange.isnot(None))
    )
    return {"exchanges": [r[0] for r in result.all()]}


@router.get("/meta/sectors")
async def get_sectors(db: AsyncSession = Depends(get_db)):
    """Get all unique sectors."""
    result = await db.execute(
        select(Company.sector).distinct().where(Company.sector.isnot(None))
    )
    return {"sectors": [r[0] for r in result.all()]}


@router.get("/{ticker}/news")
async def get_company_news(
    ticker: str,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=1, le=50),
):
    """Get recent news articles for a ticker from Finnhub (last N days)."""
    ticker = ticker.upper()
    cache_key = f"company_news:{ticker}:{days}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not FINNHUB_API_KEY:
        return {"ticker": ticker, "articles": [], "error": "Finnhub API key not configured"}

    today = date.today()
    start = (today - timedelta(days=days)).isoformat()
    end = today.isoformat()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": ticker,
                    "from": start,
                    "to": end,
                    "token": FINNHUB_API_KEY,
                },
            )
            if resp.status_code != 200:
                return {"ticker": ticker, "articles": []}
            raw = resp.json()
    except Exception as e:
        logger.error(f"Finnhub news error for {ticker}: {e}")
        return {"ticker": ticker, "articles": []}

    if not isinstance(raw, list):
        return {"ticker": ticker, "articles": []}

    articles = []
    for item in raw[:limit]:
        articles.append({
            "id": item.get("id"),
            "headline": item.get("headline"),
            "summary": item.get("summary"),
            "source": item.get("source"),
            "url": item.get("url"),
            "image": item.get("image"),
            "datetime": item.get("datetime"),  # unix timestamp
            "category": item.get("category"),
            "related": item.get("related"),
        })

    response = {
        "ticker": ticker,
        "articles": articles,
        "total": len(articles),
        "date_range": {"start": start, "end": end},
    }
    cache.set(cache_key, response, 900)  # 15 minutes
    return response
