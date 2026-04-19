from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.company import Company
from app.services.trade_analyzer import analyze_trade
from app.cache.memory_cache import cache
from app.config import CACHE_TTL_ANALYSIS, BIOTECH_SIC_CODES
from app.rate_limit import limiter

router = APIRouter(prefix="/api/analyzer", tags=["analyzer"])


# Each analysis call hits Anthropic and costs real money. 5/min per IP is
# plenty for a logged-in user clicking around, stops cost-amplifying abuse.
@router.post("/{ticker}")
@limiter.limit("5/minute")
async def run_analysis(
    request: Request,
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Run AI-powered trade analysis for a company."""
    ticker = ticker.upper()

    # Check cache
    cache_key = f"analysis:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Verify company exists
    result = await db.execute(select(Company).where(Company.ticker == ticker))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    # Run analysis
    analysis = await analyze_trade(db, ticker)

    if "error" in analysis:
        raise HTTPException(status_code=400, detail=analysis["error"])

    # Cache for 5 minutes
    cache.set(cache_key, analysis, CACHE_TTL_ANALYSIS)

    return analysis


@router.get("/tickers")
async def get_analyzer_tickers(
    search: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Get list of biotech tickers for autocomplete."""
    query = select(Company.ticker, Company.name).where(
        Company.sic_code.in_(BIOTECH_SIC_CODES)
    )

    if search:
        from sqlalchemy import or_
        term = f"%{search}%"
        query = query.where(
            or_(Company.ticker.ilike(term), Company.name.ilike(term))
        )

    query = query.order_by(Company.market_cap.desc().nullslast()).limit(20)
    result = await db.execute(query)
    rows = result.all()

    return {
        "tickers": [{"ticker": r[0], "name": r[1]} for r in rows],
    }
