"""
Sync biotech companies from SEC EDGAR.

Fetches all US-listed companies, filters by biotech-relevant SIC codes,
and upserts into the companies table.
"""

import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy import select

from app.models.company import Company, SponsorAlias
from app.models.sync_log import SyncLog
from app.config import SEC_USER_AGENT, SEC_TICKERS_URL, BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)


async def sync_companies(db: AsyncSession) -> int:
    """
    Fetch company list from SEC EDGAR and filter to biotech companies.
    Returns the number of companies synced.
    """
    log = SyncLog(
        sync_type="COMPANIES",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Fetch the full company list from SEC
        headers = {"User-Agent": SEC_USER_AGENT}
        async with httpx.AsyncClient() as client:
            response = await client.get(SEC_TICKERS_URL, headers=headers, timeout=30)
            response.raise_for_status()

        data = response.json()

        # The JSON structure: {"fields": [...], "data": [[...], ...]}
        fields = data.get("fields", [])
        rows = data.get("data", [])

        # Find column indices
        field_map = {f: i for i, f in enumerate(fields)}
        cik_idx = field_map.get("cik", 0)
        name_idx = field_map.get("name", 1)
        ticker_idx = field_map.get("ticker", 2)
        exchange_idx = field_map.get("exchange", 3)

        count = 0
        for row in rows:
            try:
                cik = str(row[cik_idx]).zfill(10)
                name = str(row[name_idx])
                ticker = str(row[ticker_idx]).upper()
                exchange = str(row[exchange_idx]) if len(row) > exchange_idx else None

                # Skip empty tickers or non-standard exchanges
                if not ticker or ticker == "NONE":
                    continue

                # We'll include all companies initially and filter by SIC later
                # SEC doesn't include SIC in this endpoint, so we store all
                # and will enrich with SIC data separately

                # Normalize exchange names
                exchange_map = {
                    "Nasdaq": "NASDAQ",
                    "NYSE": "NYSE",
                    "CBOE": "CBOE",
                    "Cboe": "CBOE",
                    "Cboe BZX": "CBOE",
                    "BATS": "CBOE",
                }
                exchange = exchange_map.get(exchange, exchange)

                # For now, filter by exchange (NYSE, NASDAQ only)
                valid_exchanges = {"NYSE", "NASDAQ"}
                if exchange not in valid_exchanges:
                    continue

                # Upsert company
                stmt = pg_upsert(Company).values(
                    ticker=ticker,
                    name=name,
                    cik=cik,
                    exchange=exchange,
                    updated_at=datetime.utcnow(),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={
                        "name": stmt.excluded.name,
                        "cik": stmt.excluded.cik,
                        "exchange": stmt.excluded.exchange,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await db.execute(stmt)

                # Also create a primary sponsor alias
                alias_stmt = pg_upsert(SponsorAlias).values(
                    ticker=ticker,
                    alias_name=name,
                    is_primary=True,
                )
                alias_stmt = alias_stmt.on_conflict_do_nothing(
                    index_elements=["ticker", "alias_name"],
                )
                await db.execute(alias_stmt)

                count += 1
            except Exception as e:
                logger.warning(f"Error processing row {row}: {e}")
                continue

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Company sync complete: {count} companies synced")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Company sync failed: {e}")
        raise


async def enrich_companies_with_sic(db: AsyncSession) -> int:
    """
    Fetch SIC codes for each company from SEC EDGAR submissions endpoint.
    This filters the company list down to biotech-relevant companies.
    """
    log = SyncLog(
        sync_type="COMPANIES_SIC",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Get ALL companies that don't have a SIC code yet (no limit)
        result = await db.execute(
            select(Company).where(Company.sic_code.is_(None))
        )
        companies = result.scalars().all()
        total = len(companies)

        headers = {"User-Agent": SEC_USER_AGENT}
        count = 0
        batch_size = 200

        async with httpx.AsyncClient() as client:
            for i, company in enumerate(companies):
                try:
                    if not company.cik:
                        continue

                    url = f"https://data.sec.gov/submissions/CIK{company.cik}.json"
                    resp = await client.get(url, headers=headers, timeout=15)

                    if resp.status_code == 200:
                        data = resp.json()
                        sic = data.get("sic", "")
                        company.sic_code = sic

                        if not company.sector:
                            company.sector = data.get("sicDescription", "")

                        count += 1

                    # Rate limit: max 10 req/sec for SEC
                    await asyncio.sleep(0.15)

                    # Commit every batch_size companies for progress visibility
                    if (i + 1) % batch_size == 0:
                        await db.commit()
                        log.records_processed = count
                        await db.commit()
                        logger.info(f"SIC enrichment progress: {i+1}/{total} processed, {count} enriched")

                except Exception as e:
                    logger.warning(f"Error enriching {company.ticker}: {e}")
                    continue

        await db.commit()

        # Do NOT delete non-biotech companies — filter at query time instead
        # This preserves all company data for potential future use

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"SIC enrichment complete: {count}/{total} companies enriched")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"SIC enrichment failed: {e}")
        raise
