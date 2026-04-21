"""Ingest biotech news from RSS feeds.

Sources (all free, no key needed):
- Endpoints News: https://endpts.com/feed/
- Fierce Biotech: https://www.fiercebiotech.com/rss/xml
- STAT:           https://www.statnews.com/feed/

For each story we extract any tickers mentioned in title + summary by
regex-matching against the `companies` table. Ticker matches go into a
text[] column so the frontend can filter per-company.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

import feedparser
import httpx
from dateutil import parser as dateparser
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.news import NewsItem
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


FEEDS: list[tuple[str, str]] = [
    ("Endpoints", "https://endpts.com/feed/"),
    ("Fierce Biotech", "https://www.fiercebiotech.com/rss/xml"),
    ("STAT", "https://www.statnews.com/feed/"),
]


# Match any $TICKER or (NYSE: TICKER) / (NASDAQ: TICKER) pattern.
_TICKER_RE = re.compile(
    r"(?:\$([A-Z]{1,6})|\b(?:NYSE|NASDAQ|Nasdaq)\s*:\s*([A-Z]{1,6})\b)"
)


def _strip_tags(html: str) -> str:
    """Light-weight tag stripper — we just want body text for summary + ticker scan."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


async def _extract_tickers(db: AsyncSession, text: str) -> list[str]:
    """Return a sorted list of ticker symbols in `text` that exist in our DB."""
    if not text:
        return []
    candidates: set[str] = set()
    for m in _TICKER_RE.finditer(text):
        t = (m.group(1) or m.group(2) or "").upper().strip()
        if t and 1 <= len(t) <= 6:
            candidates.add(t)
    if not candidates:
        return []
    result = await db.execute(
        select(Company.ticker).where(Company.ticker.in_(candidates))
    )
    return sorted({r[0] for r in result.all()})


async def _fetch_feed(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        resp = await client.get(
            url,
            headers={
                "User-Agent": "BiotickNewsBot/1.0 (+https://biotick.io)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.warning(f"RSS {url} returned {resp.status_code}")
            return None
        return resp.content
    except Exception as e:
        logger.warning(f"RSS {url} fetch failed: {e}")
        return None


async def sync_news(db: AsyncSession) -> int:
    """Fetch all feeds, upsert unique stories, return count inserted."""
    log = SyncLog(sync_type="NEWS", started_at=datetime.utcnow(), status="RUNNING")
    db.add(log)
    await db.commit()

    inserted = 0
    try:
        async with httpx.AsyncClient() as client:
            for source, url in FEEDS:
                body = await _fetch_feed(client, url)
                if not body:
                    continue

                feed = feedparser.parse(body)
                if feed.bozo and not feed.entries:
                    logger.warning(f"Failed to parse {source} feed at {url}")
                    continue

                for entry in feed.entries[:40]:  # newest 40 per source per run
                    try:
                        title = (entry.get("title") or "").strip()
                        link = (entry.get("link") or "").strip()
                        if not title or not link:
                            continue

                        summary_html = (
                            entry.get("summary")
                            or entry.get("description")
                            or ""
                        )
                        summary_text = _strip_tags(summary_html)

                        # Published date — feedparser normalizes but some feeds
                        # vary. Fall back to dateutil on a raw string.
                        pub_struct = (
                            entry.get("published_parsed")
                            or entry.get("updated_parsed")
                        )
                        if pub_struct:
                            published_at = datetime(*pub_struct[:6], tzinfo=timezone.utc)
                        elif entry.get("published"):
                            try:
                                published_at = dateparser.parse(entry["published"])
                            except Exception:
                                published_at = None
                        else:
                            published_at = None

                        tickers = await _extract_tickers(
                            db, f"{title} {summary_text}"
                        )

                        async with db.begin_nested():
                            stmt = pg_upsert(NewsItem).values(
                                source=source,
                                title=title[:500],
                                url=link[:1000],
                                summary=summary_text or None,
                                published_at=published_at,
                                tickers=tickers,
                            )
                            # If we've seen the URL before, refresh tickers/summary
                            # in case of late ticker mentions or edits upstream.
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["url"],
                                set_={
                                    "title": stmt.excluded.title,
                                    "summary": stmt.excluded.summary,
                                    "published_at": stmt.excluded.published_at,
                                    "tickers": stmt.excluded.tickers,
                                },
                            )
                            await db.execute(stmt)
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Error on {source} entry: {e}")
                        continue

                # Commit per source so we don't lose work if a later source blows up.
                await db.commit()
                # Tiny pause between sources — be nice to origins.
                await asyncio.sleep(1.0)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = inserted
        await db.commit()
        logger.info(f"News sync complete: {inserted} items processed")
        return inserted

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"News sync failed: {e}")
        raise
