"""
Fetch FDA drug approval data from OpenFDA API.

Creates catalyst entries for FDA approval events and maps them
to biotech companies where possible.
"""

import asyncio
import logging
from datetime import datetime, date

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from rapidfuzz import fuzz, process

from app.models.company import Company, SponsorAlias
from app.models.catalyst import Catalyst
from app.models.sync_log import SyncLog
from app.config import BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)

OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"


async def sync_fda_approvals(db: AsyncSession) -> int:
    """Fetch recent FDA drug approvals and create catalyst entries."""
    log = SyncLog(
        sync_type="FDA_APPROVALS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Load company aliases for matching
        result = await db.execute(
            select(SponsorAlias, Company.name).join(
                Company, SponsorAlias.ticker == Company.ticker
            ).where(Company.sic_code.in_(BIOTECH_SIC_CODES))
        )
        rows = result.all()

        alias_to_ticker: dict[str, str] = {}
        all_aliases: list[str] = []
        for alias, company_name in rows:
            norm = alias.alias_name.lower().strip()
            alias_to_ticker[norm] = alias.ticker
            all_aliases.append(norm)
            norm_name = company_name.lower().strip()
            if norm_name not in alias_to_ticker:
                alias_to_ticker[norm_name] = alias.ticker
                all_aliases.append(norm_name)

        count = 0

        # Fetch recent FDA approvals (last 2 years)
        async with httpx.AsyncClient(timeout=30) as client:
            for skip in range(0, 500, 100):
                try:
                    resp = await client.get(OPENFDA_URL, params={
                        "search": "submissions.submission_type:ORIG AND submissions.submission_status:AP",
                        "limit": 100,
                        "skip": skip,
                    })

                    if resp.status_code != 200:
                        logger.warning(f"OpenFDA returned {resp.status_code}")
                        break

                    data = resp.json()
                    results = data.get("results", [])

                    if not results:
                        break

                    for drug in results:
                        try:
                            sponsor = drug.get("sponsor_name", "")
                            brand_name = ""
                            generic_name = ""

                            products = drug.get("products", [])
                            if products:
                                brand_name = products[0].get("brand_name", "")
                                generic_name = products[0].get("active_ingredients", [{}])[0].get("name", "") if products[0].get("active_ingredients") else ""

                            # Find approval submissions
                            submissions = drug.get("submissions", [])
                            for sub in submissions:
                                if sub.get("submission_type") == "ORIG" and sub.get("submission_status") == "AP":
                                    approval_date_str = sub.get("submission_status_date")
                                    if not approval_date_str:
                                        continue

                                    try:
                                        approval_date = datetime.strptime(approval_date_str, "%Y%m%d").date()
                                    except ValueError:
                                        continue

                                    # Only recent approvals (last 3 years)
                                    if (date.today() - approval_date).days > 1095:
                                        continue

                                    # Match sponsor to company
                                    ticker = None
                                    sponsor_lower = sponsor.lower().strip()
                                    ticker = alias_to_ticker.get(sponsor_lower)

                                    if not ticker and all_aliases:
                                        match = process.extractOne(
                                            sponsor_lower,
                                            all_aliases,
                                            scorer=fuzz.token_sort_ratio,
                                            score_cutoff=80,
                                        )
                                        if match:
                                            ticker = alias_to_ticker.get(match[0])

                                    if not ticker:
                                        continue

                                    drug_display = brand_name or generic_name or "Unknown drug"
                                    description = f"FDA Approval: {drug_display}"
                                    if generic_name and brand_name:
                                        description = f"FDA Approval: {brand_name} ({generic_name})"

                                    is_past = approval_date < date.today()

                                    stmt = pg_upsert(Catalyst).values(
                                        company_ticker=ticker,
                                        drug_name=drug_display,
                                        event_type="FDA_APPROVAL",
                                        event_description=description,
                                        expected_date=approval_date,
                                        date_precision="EXACT",
                                        significance_score=10,
                                        confidence="HIGH",
                                        source="OpenFDA",
                                        source_url=f"https://www.accessdata.fda.gov/scripts/cder/daf/",
                                        is_past=is_past,
                                        outcome="POSITIVE" if is_past else "PENDING",
                                        updated_at=datetime.utcnow(),
                                    )
                                    stmt = stmt.on_conflict_do_nothing(
                                        index_elements=["company_ticker", "drug_name", "event_type", "expected_date"],
                                    )
                                    await db.execute(stmt)
                                    count += 1

                        except Exception as e:
                            logger.debug(f"Error processing FDA drug: {e}")
                            continue

                    await db.commit()
                    logger.info(f"FDA sync page {skip//100 + 1}: {count} approvals so far")

                    await asyncio.sleep(0.5)  # OpenFDA rate limit

                except Exception as e:
                    logger.warning(f"Error fetching FDA page: {e}")
                    break

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"FDA calendar sync complete: {count} approvals added")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"FDA calendar sync failed: {e}")
        raise
