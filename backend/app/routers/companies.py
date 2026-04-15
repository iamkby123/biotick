from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from math import ceil

from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyListItem, CompanyListResponse, CompanyDetail
from app.cache.memory_cache import cache
from app.config import CACHE_TTL_SCREENER, CACHE_TTL_COMPANY_DETAIL, BIOTECH_SIC_CODES

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    search: str | None = Query(None, description="Search by ticker or company name"),
    exchange: str | None = Query(None),
    min_market_cap: float | None = Query(None),
    max_market_cap: float | None = Query(None),
    sector: str | None = Query(None),
    therapeutic_area: str | None = Query(None),
    sort_by: str = Query("market_cap", description="Sort field"),
    sort_dir: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List and search biotech companies with filtering and pagination."""
    # Build cache key from params
    cache_key = f"companies:{search}:{exchange}:{min_market_cap}:{max_market_cap}:{sector}:{therapeutic_area}:{sort_by}:{sort_dir}:{page}:{per_page}"
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
