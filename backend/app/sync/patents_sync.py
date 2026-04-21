"""Populate the `patents` table from the USPTO PatentsView API.

API: https://search.patentsview.org/api/v1/patent/ (POST, JSON body).

As of 2024 PatentsView requires a free API key (45 req/min on free tier).
Set PATENTSVIEW_API_KEY in the env. If missing, this sync logs a warning
and exits cleanly rather than raising — the rest of the app keeps running.

For each company we match patents whose assignee_organization contains the
company name (normalized). This replaces the earlier Google Patents scrape
that got rate-limited after ~128 patents.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, date, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.patent import Patent
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_API_URL = "https://search.patentsview.org/api/v1/patent/"


def _normalize_for_match(name: str) -> str:
    """Strip common corporate suffixes + lowercase for fuzzy assignee match."""
    s = name.lower()
    s = re.sub(r",?\s+(inc\.?|corp\.?|corporation|ltd\.?|plc|llc|co\.?|holdings?|pharmaceuticals?|therapeutics|biosciences?|biotech)$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _expiration_from_filing(filing_date: date | None) -> date | None:
    """US utility patents expire 20y from filing. Approximation — ignores
    PTA/PTE extensions and maintenance-fee lapses, but good enough for UX."""
    if not filing_date:
        return None
    try:
        return filing_date.replace(year=filing_date.year + 20)
    except ValueError:
        # Leap-day edge case
        return filing_date + timedelta(days=365 * 20)


async def _fetch_patents_for_company(
    client: httpx.AsyncClient,
    company_name: str,
    api_key: str,
    limit: int = 50,
) -> list[dict]:
    """Return raw patent records for a company, newest first."""
    # Use ID query to get patents whose assignee organization contains the
    # company name (case-insensitive). The PatentsView query language allows
    # `_text_any` for a substring-contains match on the assignees.organization.
    body = {
        "q": {"_text_any": {"assignees.assignee_organization": company_name}},
        "f": [
            "patent_id",
            "patent_title",
            "patent_date",
            "patent_abstract",
            "patent_type",
            "assignees.assignee_organization",
            "application.filing_date",
        ],
        "s": [{"patent_date": "desc"}],
        "o": {"size": limit},
    }

    try:
        resp = await client.post(
            _API_URL,
            json=body,
            headers={
                "X-Api-Key": api_key,
                "Content-Type": "application/json",
                "User-Agent": "BiotickPatents/1.0 (+https://biotick.io)",
            },
            timeout=25,
        )
    except Exception as e:
        logger.warning(f"PatentsView fetch failed for {company_name}: {e}")
        return []

    if resp.status_code == 429:
        logger.warning("PatentsView rate-limit hit; sleeping 60s")
        await asyncio.sleep(60)
        return []
    if resp.status_code != 200:
        logger.warning(
            f"PatentsView {company_name!r}: {resp.status_code} {resp.text[:200]}"
        )
        return []

    try:
        return (resp.json() or {}).get("patents", []) or []
    except Exception as e:
        logger.warning(f"PatentsView bad JSON for {company_name}: {e}")
        return []


async def sync_patents(db: AsyncSession, limit_companies: int | None = None) -> int:
    """Re-populate patents for every company using PatentsView."""
    api_key = os.environ.get("PATENTSVIEW_API_KEY", "").strip()
    if not api_key:
        logger.warning("PATENTSVIEW_API_KEY not set — skipping patents sync")
        return 0

    log = SyncLog(sync_type="PATENTS", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        q = select(Company.ticker, Company.name).order_by(Company.ticker)
        if limit_companies:
            q = q.limit(limit_companies)
        companies = (await db.execute(q)).all()

        total_inserted = 0
        async with httpx.AsyncClient() as client:
            for ticker, name in companies:
                if not name:
                    continue

                records = await _fetch_patents_for_company(client, name, api_key)

                expected_match = _normalize_for_match(name)
                batch = 0
                for rec in records:
                    try:
                        patent_number = str(rec.get("patent_id") or "").strip()
                        if not patent_number:
                            continue

                        # Verify the assignee actually matches — PatentsView's
                        # _text_any is liberal so we double-check to avoid
                        # assigning, e.g., "Johnson & Johnson" patents to any
                        # ticker whose name contains "Johnson".
                        assignees = rec.get("assignees") or []
                        assignee_name = (
                            assignees[0].get("assignee_organization")
                            if assignees
                            else None
                        )
                        if assignee_name:
                            norm = _normalize_for_match(assignee_name)
                            if expected_match not in norm and norm not in expected_match:
                                continue

                        grant_date_str = rec.get("patent_date")
                        grant_date = (
                            datetime.strptime(grant_date_str, "%Y-%m-%d").date()
                            if grant_date_str
                            else None
                        )

                        app_arr = rec.get("application") or []
                        filing_date_str = (
                            app_arr[0].get("filing_date") if app_arr else None
                        )
                        filing_date = (
                            datetime.strptime(filing_date_str, "%Y-%m-%d").date()
                            if filing_date_str
                            else None
                        )

                        async with db.begin_nested():
                            stmt = pg_upsert(Patent).values(
                                patent_number=patent_number,
                                title=(rec.get("patent_title") or "")[:1000],
                                assignee_name=(assignee_name or "")[:300],
                                company_ticker=ticker,
                                filing_date=filing_date,
                                grant_date=grant_date,
                                expiration_date=_expiration_from_filing(filing_date),
                                abstract=(rec.get("patent_abstract") or "")[:4000],
                                patent_type=rec.get("patent_type"),
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["patent_number"],
                                set_={
                                    "title": stmt.excluded.title,
                                    "assignee_name": stmt.excluded.assignee_name,
                                    "company_ticker": stmt.excluded.company_ticker,
                                    "filing_date": stmt.excluded.filing_date,
                                    "grant_date": stmt.excluded.grant_date,
                                    "expiration_date": stmt.excluded.expiration_date,
                                    "abstract": stmt.excluded.abstract,
                                    "patent_type": stmt.excluded.patent_type,
                                },
                            )
                            await db.execute(stmt)
                        batch += 1
                        total_inserted += 1
                        if batch % 50 == 0:
                            await db.commit()
                    except Exception as e:
                        logger.warning(f"patent row error {patent_number}: {e}")
                        continue

                if batch:
                    await db.commit()
                    logger.debug(f"{ticker}: +{batch} patents")

                # Free tier is 45/min; 1.4s per company stays under.
                await asyncio.sleep(1.4)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_inserted
        await db.commit()
        logger.info(f"Patents sync: {total_inserted} upserted across {len(companies)} companies")
        return total_inserted

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Patents sync failed: {e}")
        raise
