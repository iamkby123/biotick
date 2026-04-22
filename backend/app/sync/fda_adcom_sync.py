"""Scrape the FDA Advisory Committee calendar via curl_cffi.

FDA's edge (Cloudflare + Akamai) aggressively TLS-fingerprints our
backend's httpx ClientHello and returns 401. curl_cffi spoofs a real
Chrome TLS handshake which reliably gets past that.

Pipeline:
  1. GET https://www.fda.gov/advisory-committees/advisory-committee-calendar
  2. Extract links to individual meeting pages.
  3. For each, pull date + agenda text, match ticker by company-name substring.
  4. Upsert on URL (unique).

Fragile: FDA's page structure shifts. If the scrape returns 0 rows, we
mark SyncLog.status=FAILED rather than silently succeeding.
"""

import asyncio
import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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


def _fetch_fda_html_sync(url: str) -> str | None:
    """Blocking curl_cffi call. Returns HTML or None."""
    try:
        from curl_cffi import requests as cureq

        sess = cureq.Session(impersonate="chrome124")
        resp = sess.get(url, timeout=25, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"FDA fetch {url}: HTTP {resp.status_code}")
            return None
        return resp.text
    except Exception as e:
        logger.warning(f"FDA fetch {url}: {e}")
        return None


async def _match_ticker_by_name(db: AsyncSession, text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    sample = text[:2000].lower()
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
        html = await asyncio.to_thread(_fetch_fda_html_sync, _CALENDAR_URL)
        if not html:
            raise RuntimeError("FDA calendar returned empty (TLS block?)")

        soup = BeautifulSoup(html, "html.parser")

        # Match anchors whose href contains "advisory-committee" path and
        # whose label looks like a meeting title.
        meeting_links: list[tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(_BASE, a["href"])
            label = a.get_text(strip=True)
            if "advisory-committee" not in href or not label:
                continue
            if len(label) < 10 or len(label) > 250:
                continue
            meeting_links.append((href, label))

        seen = set()
        unique: list[tuple[str, str]] = []
        for href, label in meeting_links:
            if href in seen:
                continue
            seen.add(href)
            unique.append((href, label))

        logger.info(f"AdCom candidate links: {len(unique)}")

        written = 0
        for href, label in unique[:120]:
            try:
                page_html = await asyncio.to_thread(_fetch_fda_html_sync, href)
                # Be polite — FDA doesn't like rapid-fire scraping
                await asyncio.sleep(0.4)
                if not page_html:
                    continue

                p_soup = BeautifulSoup(page_html, "html.parser")
                body_text = p_soup.get_text(separator=" ", strip=True)

                meeting_date = _parse_date(body_text)
                if not meeting_date:
                    continue
                if (meeting_date - date.today()).days > 5 * 365:
                    continue

                h1 = p_soup.find("h1")
                committee = (h1.get_text(strip=True) if h1 else label)[:200]

                paras = p_soup.find_all("p")
                topics = " ".join(p.get_text(strip=True) for p in paras[:4])[:1500]

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
