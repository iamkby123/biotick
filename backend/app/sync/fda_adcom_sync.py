"""Scrape the FDA Advisory Committee calendar.

Source: https://www.fda.gov/advisory-committees/advisory-committee-calendar
        (and each committee's per-page schedule)

This is a fragile scrape — FDA's page layout changes occasionally. We:
  1. Fetch the index page and pull out `<a>` links that look like meeting pages.
  2. For each meeting page, extract committee name, date, agenda text.
  3. Best-effort drug-name + company-ticker match via substring + companies table.
  4. Upsert on URL (unique) so reruns are idempotent.

If the page structure changes, SyncLog.status = FAILED and the rest of
the app keeps running.
"""

import asyncio
import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import SEC_USER_AGENT
from app.models.adcom import AdComMeeting
from app.models.company import Company
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

_CALENDAR_URL = "https://www.fda.gov/advisory-committees/advisory-committee-calendar"
_BASE = "https://www.fda.gov"

_DATE_RE = re.compile(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def _parse_date(raw: str) -> date | None:
    m = _DATE_RE.search(raw)
    if not m:
        return None
    try:
        parts = re.split(r"[,\s]+", m.group(1).strip())
        month = _MONTHS.get(parts[0])
        day = int(parts[1])
        year = int(parts[2])
        if month:
            return date(year, month, day)
    except (ValueError, IndexError, KeyError):
        pass
    return None


async def _match_ticker_by_name(db: AsyncSession, text: str) -> tuple[str | None, str | None]:
    """Return (drug_name_candidate, ticker) by scanning `text` for any
    company name we know about. Conservative — only matches full multi-word
    names to avoid false positives."""
    if not text:
        return None, None
    sample = text[:2000].lower()
    result = await db.execute(select(Company.ticker, Company.name))
    best_ticker, best_name = None, None
    for ticker, name in result.all():
        if not name or len(name) < 6:
            continue
        norm = re.sub(r",?\s+(inc\.?|corp\.?|ltd\.?|plc|llc)$", "", name, flags=re.IGNORECASE).strip()
        if norm.lower() in sample:
            best_ticker, best_name = ticker, norm
            break
    return best_name, best_ticker


async def sync_fda_adcom(db: AsyncSession) -> int:
    log = SyncLog(sync_type="FDA_ADCOM", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _CALENDAR_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=20,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"FDA calendar returned {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")

            # FDA's calendar renders meeting rows as <tr> or as list items;
            # we match any anchor whose href contains "advisory-committees"
            # and whose text looks like a meeting title.
            meeting_links: list[tuple[str, str]] = []
            for a in soup.find_all("a", href=True):
                href = urljoin(_BASE, a["href"])
                label = a.get_text(strip=True)
                if "advisory-committees" not in href or not label:
                    continue
                if len(label) < 10 or len(label) > 250:
                    continue
                meeting_links.append((href, label))

            # Deduplicate
            seen = set()
            unique: list[tuple[str, str]] = []
            for href, label in meeting_links:
                if href in seen:
                    continue
                seen.add(href)
                unique.append((href, label))

            logger.info(f"AdCom candidate links: {len(unique)}")

            written = 0
            for href, label in unique[:100]:  # cap to avoid scraping all of fda.gov
                try:
                    page = await client.get(
                        href,
                        headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                        timeout=15,
                        follow_redirects=True,
                    )
                    await asyncio.sleep(0.5)
                    if page.status_code != 200:
                        continue
                    p_soup = BeautifulSoup(page.text, "html.parser")
                    body_text = p_soup.get_text(separator=" ", strip=True)

                    meeting_date = _parse_date(body_text)
                    if not meeting_date:
                        continue
                    # Skip anything more than 5 years out — probably not a real meeting page
                    if (meeting_date - date.today()).days > 5 * 365:
                        continue

                    # Heuristic: first <h1> is the meeting title; use page title as committee
                    h1 = p_soup.find("h1")
                    committee = (
                        h1.get_text(strip=True) if h1 else label
                    )[:200]

                    # Topics blurb — first few paragraphs
                    paras = p_soup.find_all("p")
                    topics = " ".join(
                        p.get_text(strip=True) for p in paras[:4]
                    )[:1500]

                    drug_name, ticker = await _match_ticker_by_name(db, topics)

                    async with db.begin_nested():
                        stmt = pg_upsert(AdComMeeting).values(
                            committee=committee,
                            meeting_date=meeting_date,
                            topics=topics,
                            drug_name=drug_name,
                            company_ticker=ticker,
                            url=href,
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
                    logger.warning(f"AdCom page {href}: {e}")
                    continue
            await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"FDA AdCom sync: {written} meetings")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"FDA AdCom sync failed: {e}")
        raise
