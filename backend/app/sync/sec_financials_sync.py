"""
Fetch financial data from SEC EDGAR XBRL company facts API.

Fills in revenue, shares outstanding, employees, and other data
that Finnhub may not have (foreign companies, micro-caps, delisted).
No API key needed — just SEC User-Agent.
"""

import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.sync_log import SyncLog
from app.config import SEC_USER_AGENT, BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)


async def sync_sec_financials(db: AsyncSession) -> int:
    """Fill in financial data from SEC EDGAR XBRL for companies missing data."""
    log = SyncLog(
        sync_type="SEC_FINANCIALS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Get companies missing key financial data
        result = await db.execute(
            select(Company).where(
                Company.sic_code.in_(BIOTECH_SIC_CODES),
                Company.cik.isnot(None),
                Company.revenue.is_(None),
            ).limit(500)
        )
        companies = result.scalars().all()
        total = len(companies)
        count = 0

        headers = {"User-Agent": SEC_USER_AGENT}

        async with httpx.AsyncClient(headers=headers, timeout=15) as client:
            for i, company in enumerate(companies):
                try:
                    cik = company.cik.lstrip("0") if company.cik else None
                    if not cik:
                        continue

                    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company.cik}.json"
                    resp = await client.get(url)

                    if resp.status_code != 200:
                        await asyncio.sleep(0.12)
                        continue

                    data = resp.json()
                    facts = data.get("facts", {})
                    us_gaap = facts.get("us-gaap", {})
                    dei = facts.get("dei", {})

                    # Revenue
                    revenue_data = us_gaap.get("Revenues") or us_gaap.get("RevenueFromContractWithCustomerExcludingAssessedTax") or us_gaap.get("SalesRevenueNet")
                    if revenue_data and not company.revenue:
                        units = revenue_data.get("units", {}).get("USD", [])
                        # Get most recent annual value
                        annual = [u for u in units if u.get("form") in ("10-K", "20-F") and u.get("val")]
                        if annual:
                            company.revenue = annual[-1]["val"]

                    # Shares outstanding
                    shares_data = dei.get("EntityCommonStockSharesOutstanding")
                    if shares_data and not company.shares_outstanding:
                        units = shares_data.get("units", {}).get("shares", [])
                        if units:
                            company.shares_outstanding = units[-1].get("val")
                            # Calculate market cap
                            if company.price and company.shares_outstanding:
                                company.market_cap = company.price * company.shares_outstanding

                    # Employees
                    emp_data = dei.get("EntityNumberOfEmployees")
                    if emp_data and not company.employees:
                        units = emp_data.get("units", {}).get("pure", [])
                        if units:
                            company.employees = int(units[-1].get("val", 0))

                    # Net income (for profit margin)
                    ni_data = us_gaap.get("NetIncomeLoss")
                    if ni_data and company.revenue and company.revenue > 0 and not company.profit_margin:
                        units = ni_data.get("units", {}).get("USD", [])
                        annual = [u for u in units if u.get("form") in ("10-K", "20-F") and u.get("val")]
                        if annual:
                            net_income = annual[-1]["val"]
                            company.profit_margin = net_income / company.revenue

                    company.updated_at = datetime.utcnow()
                    count += 1

                    await asyncio.sleep(0.12)  # SEC rate limit

                    if (i + 1) % 50 == 0:
                        await db.commit()
                        logger.info(f"SEC financials: {i+1}/{total} ({count} updated)")

                except Exception as e:
                    logger.debug(f"Error for {company.ticker}: {e}")
                    await asyncio.sleep(0.12)
                    continue

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"SEC financials complete: {count}/{total} updated")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"SEC financials failed: {e}")
        raise
