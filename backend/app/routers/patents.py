"""
Patent endpoints — USPTO patents assigned to biotech companies.

Powered by the `patents` table populated by `backend/scripts/sync_patents.py`.
"""

import logging
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.patent import Patent
from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/companies", tags=["patents"])


@router.get("/{ticker}/patents")
async def get_company_patents(
    ticker: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get patents for a company (paginated, sorted by grant_date desc)."""
    ticker = ticker.upper()
    cache_key = f"patents:{ticker}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    base_query = select(Patent).where(Patent.company_ticker == ticker)

    # Count total
    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort and paginate
    query = (
        base_query
        .order_by(Patent.grant_date.desc().nullslast(), Patent.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    patents = result.scalars().all()

    response = {
        "ticker": ticker,
        "patents": [
            {
                "id": p.id,
                "patent_number": p.patent_number,
                "title": p.title,
                "assignee_name": p.assignee_name,
                "company_ticker": p.company_ticker,
                "filing_date": p.filing_date.isoformat() if p.filing_date else None,
                "grant_date": p.grant_date.isoformat() if p.grant_date else None,
                "expiration_date": (
                    p.expiration_date.isoformat() if p.expiration_date else None
                ),
                "abstract": p.abstract,
                "patent_type": p.patent_type,
                "uspto_url": (
                    f"https://patents.google.com/patent/US{p.patent_number}"
                    if p.patent_number else None
                ),
            }
            for p in patents
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }
    cache.set(cache_key, response, 1800)  # 30 min
    return response
