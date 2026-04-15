"""
Enrich companies with detailed info from SEC EDGAR.

Uses the submissions endpoint which includes address, phone, entity type,
state of incorporation, and other metadata. No rate limit issues like yfinance.
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

# US state codes to full names
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


async def sync_company_info_from_edgar(db: AsyncSession) -> int:
    """
    Enrich biotech companies with address, phone, and metadata from SEC EDGAR.
    Much more reliable than yfinance — no aggressive rate limiting.
    """
    log = SyncLog(
        sync_type="COMPANY_INFO_EDGAR",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Get biotech companies missing info
        result = await db.execute(
            select(Company).where(
                Company.sic_code.in_(BIOTECH_SIC_CODES),
                Company.cik.isnot(None),
                Company.city.is_(None),  # Not yet enriched
            )
        )
        companies = result.scalars().all()
        total = len(companies)

        headers = {"User-Agent": SEC_USER_AGENT}
        count = 0

        async with httpx.AsyncClient(headers=headers, timeout=15) as client:
            for i, company in enumerate(companies):
                try:
                    url = f"https://data.sec.gov/submissions/CIK{company.cik}.json"
                    resp = await client.get(url)

                    if resp.status_code != 200:
                        await asyncio.sleep(0.12)
                        continue

                    data = resp.json()

                    # Address
                    biz_addr = data.get("addresses", {}).get("business", {})
                    if biz_addr:
                        street = biz_addr.get("street1", "")
                        street2 = biz_addr.get("street2", "")
                        company.address = f"{street} {street2}".strip() if street else None

                        city = biz_addr.get("city", "")
                        company.city = city.title() if city else None

                        state_code = biz_addr.get("stateOrCountry", "")
                        company.state = STATE_NAMES.get(state_code, state_code) if state_code else None
                        company.zip_code = biz_addr.get("zipCode")

                        # Country
                        if biz_addr.get("isForeignLocation"):
                            country_desc = biz_addr.get("stateOrCountryDescription", "")
                            company.country = country_desc if country_desc else None
                        else:
                            company.country = "United States"

                    # Phone
                    phone = data.get("phone")
                    if phone:
                        company.phone = phone

                    # Entity info
                    category = data.get("category", "")
                    entity_type = data.get("entityType", "")

                    # State of incorporation (can differ from HQ)
                    state_inc = data.get("stateOfIncorporation", "")

                    # Former names can give us founding info
                    former_names = data.get("formerNames", [])
                    if former_names:
                        # Earliest former name date approximates founding
                        earliest = min(
                            (fn.get("from", "9999") for fn in former_names),
                            default=None,
                        )
                        if earliest and earliest != "9999":
                            company.founded_year = earliest[:4]

                    # Fiscal year end
                    fye = data.get("fiscalYearEnd", "")

                    company.updated_at = datetime.utcnow()
                    count += 1

                    # SEC rate limit: 10 req/sec
                    await asyncio.sleep(0.12)

                    # Commit every 100 companies
                    if (i + 1) % 100 == 0:
                        await db.commit()
                        logger.info(f"Company info progress: {i+1}/{total} ({count} enriched)")

                except Exception as e:
                    logger.warning(f"Error enriching {company.ticker}: {e}")
                    await asyncio.sleep(0.12)
                    continue

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Company info sync complete: {count}/{total} enriched from EDGAR")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Company info sync failed: {e}")
        raise
