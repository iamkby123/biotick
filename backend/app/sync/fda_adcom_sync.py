"""FDA Advisory Committee meeting calendar via the Federal Register API.

We originally scraped fda.gov/advisory-committees/advisory-committee-calendar,
but Akamai's WAF blocks Fly's datacenter IP range (401 regardless of TLS
fingerprint).

Federal Register IS the authoritative source — by statute, FDA must
publish all advisory-committee meeting notices there 15+ days in
advance. The Federal Register has a clean free JSON API at:
    https://www.federalregister.gov/api/v1/documents.json

Query shape:
    conditions[type][]=NOTICE
    conditions[term]=advisory+committee+meeting
    conditions[agencies][]=food-and-drug-administration
    per_page=200
    order=newest

Each notice gives us:
- title (committee name + "Notice of Meeting")
- publication_date
- dates (plain-English meeting date, e.g. "The meeting will be held on July 23, 2026...")
- abstract (description we can scan for drug names)
- html_url (back-link)
"""

import asyncio
import logging
import re
from datetime import date, datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.adcom import AdComMeeting
from app.models.company import Company
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_API_URL = "https://www.federalregister.gov/api/v1/documents.json"

# Look for dates like "July 23, 2026" or "on October 5-6, 2026"
_MEETING_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2})(?:\s*[-–]\s*\d{1,2})?,\s+(\d{4})",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_first_date(text: str) -> date | None:
    if not text:
        return None
    m = _MEETING_DATE_RE.search(text)
    if not m:
        return None
    try:
        month = _MONTHS.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3))
        if month:
            return date(year, month, day)
    except (ValueError, IndexError, KeyError):
        pass
    return None


def _committee_from_title(title: str) -> str:
    """The FR title is typically '<Committee>; Notice of Meeting; ...'
    We want just the committee."""
    if not title:
        return ""
    first = title.split(";")[0].strip()
    return first[:200]


async def _match_ticker_by_name(
    db: AsyncSession, text: str
) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    sample = text[:3000].lower()
    result = await db.execute(select(Company.ticker, Company.name))
    for ticker, name in result.all():
        if not name or len(name) < 6:
            continue
        norm = re.sub(
            r",?\s+(inc\.?|corp\.?|ltd\.?|plc|llc)$", "", name, flags=re.IGNORECASE
        ).strip()
        if norm.lower() in sample:
            return norm, ticker
    return None, None


async def sync_fda_adcom(db: AsyncSession) -> int:
    log = SyncLog(sync_type="FDA_ADCOM", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        written = 0
        async with httpx.AsyncClient() as client:
            # Pull the most recent 200 advisory-committee notices.
            # fields[]=dates is REQUIRED — without it the list endpoint
            # omits the `dates` field (where the meeting date lives).
            params = [
                ("conditions[type][]", "NOTICE"),
                ("conditions[term]", "advisory committee meeting"),
                ("conditions[agencies][]", "food-and-drug-administration"),
                ("per_page", "200"),
                ("order", "newest"),
                ("fields[]", "title"),
                ("fields[]", "publication_date"),
                ("fields[]", "dates"),
                ("fields[]", "abstract"),
                ("fields[]", "html_url"),
                ("fields[]", "document_number"),
            ]
            try:
                resp = await client.get(_API_URL, params=params, timeout=30)
            except Exception as e:
                raise RuntimeError(f"Federal Register API failed: {e}")
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Federal Register API returned {resp.status_code}"
                )
            data = resp.json() or {}
            results = data.get("results") or []
            logger.info(f"Federal Register notices fetched: {len(results)}")

            for r in results:
                try:
                    title = r.get("title") or ""
                    url = r.get("html_url") or ""
                    if not url:
                        continue
                    # Filter to actual meeting notices — skip charter renewals,
                    # FR corrections, etc.
                    if "notice of meeting" not in title.lower():
                        continue

                    committee = _committee_from_title(title)

                    # Meeting date lives in the `dates` field
                    dates_text = r.get("dates") or ""
                    abstract = r.get("abstract") or ""
                    meeting_date = _parse_first_date(dates_text) or _parse_first_date(
                        abstract
                    )
                    if not meeting_date:
                        continue
                    # Skip anything >5 years out
                    if (meeting_date - date.today()).days > 5 * 365:
                        continue
                    # Skip anything 2+ years in the past — old notices not
                    # useful to investors.
                    if (date.today() - meeting_date).days > 2 * 365:
                        continue

                    topics = (abstract or dates_text)[:1500]
                    drug_name, ticker = await _match_ticker_by_name(db, topics)

                    async with db.begin_nested():
                        stmt = pg_upsert(AdComMeeting).values(
                            committee=committee,
                            meeting_date=meeting_date,
                            topics=topics,
                            drug_name=drug_name,
                            company_ticker=ticker,
                            url=url,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["url"],
                            set_={
                                "committee": stmt.excluded.committee,
                                "meeting_date": stmt.excluded.meeting_date,
                                "topics": stmt.excluded.topics,
                                "drug_name": stmt.excluded.drug_name,
                                "company_ticker": stmt.excluded.company_ticker,
                            },
                        )
                        await db.execute(stmt)
                    written += 1
                    if written % 25 == 0:
                        await db.commit()
                except Exception as e:
                    logger.warning(f"FR notice error: {e}")
                    continue
            await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"FDA AdCom sync (Federal Register): {written} meetings")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"FDA AdCom sync failed: {e}")
        raise
