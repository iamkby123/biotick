"""
Institutional holdings endpoints — 13F "smart money" tracking.

Exposes which specialist biotech funds (RTW, Perceptive, Baker Bros, OrbiMed,
Avoro, Deep Track) hold a given ticker, based on their most recent 13F filings.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.institutional import InstitutionalHolding
from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/companies", tags=["institutional"])


def _sec_edgar_cik_url(cik: str) -> str:
    """Return the SEC EDGAR filings-browse URL for a fund CIK."""
    if not cik:
        return ""
    # EDGAR expects the CIK with leading zeros stripped for browse.
    try:
        cik_int = int(cik.lstrip("0") or "0")
    except ValueError:
        cik_int = 0
    return (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}"
        "&type=13F-HR&dateb=&owner=include&count=10"
    )


@router.get("/{ticker}/institutional")
async def get_institutional_holdings(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """
    List fund holdings (13F) for the given ticker.

    Returns the most-recent reported position per fund/quarter, newest first.
    Each row includes the SEC EDGAR filings link for the fund.
    """
    ticker = ticker.upper()
    cache_key = f"institutional:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(InstitutionalHolding)
        .where(InstitutionalHolding.ticker == ticker)
        .order_by(
            InstitutionalHolding.quarter_end.desc().nullslast(),
            InstitutionalHolding.value.desc().nullslast(),
        )
    )
    rows = result.scalars().all()

    holdings = [
        {
            "id": h.id,
            "ticker": h.ticker,
            "fund_name": h.fund_name,
            "fund_cik": h.fund_cik,
            "shares": h.shares,
            "value": h.value,
            "quarter_end": h.quarter_end.isoformat() if h.quarter_end else None,
            "filing_date": h.filing_date.isoformat() if h.filing_date else None,
            "edgar_url": _sec_edgar_cik_url(h.fund_cik),
        }
        for h in rows
    ]

    total_value = sum(h["value"] or 0 for h in holdings)
    total_shares = sum(h["shares"] or 0 for h in holdings)

    response = {
        "ticker": ticker,
        "holdings": holdings,
        "total": len(holdings),
        "total_value": total_value,
        "total_shares": total_shares,
    }
    cache.set(cache_key, response, 900)  # 15 min
    return response
