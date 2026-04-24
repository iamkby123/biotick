"""Extract exact PDUFA target action dates from press release bodies.

ClinicalTrials.gov only gives us month-precision primary-completion dates.
But when a biotech actually receives a PDUFA target action date from FDA,
they announce it via 8-K press release — and those press releases ALWAYS
contain a specific date like "PDUFA target action date of April 15, 2026".

This sync scans `press_releases.body_text` for those phrases and creates
EXACT-precision PDUFA catalyst rows. Runs purely on regex — no Claude
tokens, fast and cheap.

Patterns it catches:
  - "PDUFA target action date of July 15, 2026"
  - "PDUFA date of 15 July 2026"
  - "Prescription Drug User Fee Act (PDUFA) target action date is October 4, 2026"
  - "FDA target action date of September 30, 2026"
  - "action date in April 2026"  (month-only fallback — still better than ClinTrials)
"""

import logging
import re
from datetime import datetime, date

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalyst import Catalyst
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Strong patterns — assign EXACT precision.
# Match: "PDUFA target action date of April 15, 2026"
#        "PDUFA date of 15 April 2026"
#        "FDA action date of October 4, 2026"
_EXACT_US = re.compile(
    r"\b(?:PDUFA|prescription\s+drug\s+user\s+fee\s+act|FDA)\s+"
    r"(?:target\s+)?(?:action\s+)?date\s+(?:of\s+|is\s+|set\s+(?:for|on)\s+)?"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})",
    re.IGNORECASE | re.DOTALL,
)
_EXACT_INTL = re.compile(
    r"\b(?:PDUFA|prescription\s+drug\s+user\s+fee\s+act|FDA)\s+"
    r"(?:target\s+)?(?:action\s+)?date\s+(?:of\s+|is\s+|set\s+(?:for|on)\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.IGNORECASE | re.DOTALL,
)

# Month-only fallback (less strong, assign MONTH precision).
_MONTH_ONLY = re.compile(
    r"\b(?:PDUFA|FDA)\s+(?:target\s+)?(?:action\s+)?date\s+(?:in|of|during)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)

# Drug name extraction — best-effort. Look for drug cues near the PDUFA mention.
_DRUG_MENTION = re.compile(
    r"(?:for|of)\s+([A-Z][A-Za-z0-9\-]{2,40}(?:®|™|\*)?)",
)


def _extract_exact_date(body: str) -> tuple[date | None, str]:
    """Return (date, precision) from a press release body.

    Tries exact patterns first (US + international), then falls back to
    month-only. Returns (None, "") if nothing matches.
    """
    if not body:
        return None, ""
    m = _EXACT_US.search(body)
    if m:
        try:
            mo = _MONTHS[m.group(1).lower()]
            return date(int(m.group(3)), mo, int(m.group(2))), "EXACT"
        except (KeyError, ValueError):
            pass
    m = _EXACT_INTL.search(body)
    if m:
        try:
            mo = _MONTHS[m.group(2).lower()]
            return date(int(m.group(3)), mo, int(m.group(1))), "EXACT"
        except (KeyError, ValueError):
            pass
    m = _MONTH_ONLY.search(body)
    if m:
        try:
            mo = _MONTHS[m.group(1).lower()]
            return date(int(m.group(2)), mo, 15), "MONTH"
        except (KeyError, ValueError):
            pass
    return None, ""


def _extract_drug_name(body: str) -> str | None:
    """Best-effort drug name — matches capitalized word after 'for' or 'of'."""
    if not body:
        return None
    # Narrow to the window around the first PDUFA mention
    idx = body.lower().find("pdufa")
    if idx < 0:
        idx = body.lower().find("fda action")
    if idx < 0:
        return None
    window = body[max(0, idx - 200) : idx + 200]
    m = _DRUG_MENTION.search(window)
    if m:
        name = m.group(1).strip()
        # Avoid obvious false positives
        if name.lower() in {"fda", "pdufa", "drug"}:
            return None
        return name[:100]
    return None


async def sync_pdufa_dates_from_press_releases(db: AsyncSession) -> int:
    """Scan recent press releases for exact PDUFA target action dates and
    upsert PDUFA catalyst rows with EXACT precision."""
    log = SyncLog(
        sync_type="PDUFA_EXTRACTOR",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Pull press releases with PDUFA/FDA mentions in body_text. We
        # filter in SQL so we don't stream huge unrelated bodies through.
        rows = await db.execute(
            text(
                """
                SELECT id, ticker, accession_number, headline, body_text,
                       filed_date, url
                FROM press_releases
                WHERE body_text IS NOT NULL
                  AND (
                    body_text ILIKE '%PDUFA%'
                    OR body_text ILIKE '%target action date%'
                  )
                  AND filed_date > CURRENT_DATE - INTERVAL '540 days'
                """
            )
        )
        prs = rows.fetchall()
        logger.info(f"pdufa_extractor: scanning {len(prs)} press releases")

        written = 0
        for pr in prs:
            try:
                body = pr[4] or ""
                filed_date: date | None = pr[5]
                d, precision = _extract_exact_date(body)
                if not d:
                    continue
                # Sanity: reject dates >3y out or >90d in past relative to filing
                if filed_date:
                    if (d - filed_date).days > 3 * 365:
                        continue
                    if (filed_date - d).days > 90:
                        continue
                drug_name = _extract_drug_name(body) or "Unspecified"
                ticker = pr[1]
                if not ticker:
                    continue

                async with db.begin_nested():
                    stmt = pg_upsert(Catalyst).values(
                        company_ticker=ticker,
                        drug_name=drug_name,
                        event_type="PDUFA",
                        event_description=(pr[3] or "PDUFA target action date")[:500],
                        expected_date=d,
                        date_precision=precision,
                        significance_score=9,
                        confidence="HIGH" if precision == "EXACT" else "MEDIUM",
                        source="press_release",
                        source_url=pr[6],
                        is_past=(d < date.today()),
                        updated_at=datetime.utcnow(),
                    )
                    # Catalyst unique key is (company_ticker, drug_name,
                    # event_type, expected_date) — upsert on conflict so
                    # reruns refresh precision/source but don't duplicate.
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[
                            "company_ticker", "drug_name", "event_type", "expected_date",
                        ],
                        set_={
                            "date_precision": stmt.excluded.date_precision,
                            "source": stmt.excluded.source,
                            "source_url": stmt.excluded.source_url,
                            "confidence": stmt.excluded.confidence,
                            "is_past": stmt.excluded.is_past,
                            "updated_at": datetime.utcnow(),
                        },
                    )
                    await db.execute(stmt)
                written += 1
                if written % 50 == 0:
                    await db.commit()
            except Exception as e:
                logger.warning(f"pdufa_extractor pr={pr[0]}: {e}")
                continue
        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = written
        await db.commit()
        logger.info(f"pdufa_extractor: {written} PDUFA catalysts written")
        return written

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"pdufa_extractor failed: {e}")
        raise
