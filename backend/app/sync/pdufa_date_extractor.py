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
# The pattern matches capitalized words that look like drug names, but we
# explicitly reject common false positives (months, generic english words,
# boilerplate filing labels).
_DRUG_MENTION_BEFORE = re.compile(
    # "... PDUFA target action date for <DRUG> of April 15, 2026"
    # "... PDUFA date for <DRUG> is ..."
    r"(?:date|pdufa)\s+(?:for|of)\s+"
    r"([A-Z][A-Za-z0-9\-]{2,40}(?:®|™|\*|\s+\([A-Za-z]+[0-9\-]+\))?)",
    re.IGNORECASE,
)
_DRUG_MENTION_APP = re.compile(
    # "application for <DRUG>" / "NDA for <DRUG>" / "BLA for <DRUG>"
    r"(?:application|submission|NDA|BLA|sBLA|sNDA)\s+for\s+"
    r"([A-Z][A-Za-z0-9\-]{2,40}(?:®|™|\*)?)",
)

_DRUG_BLACKLIST = {
    # Months
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    # PDUFA / regulatory boilerplate
    "pdufa", "fda", "drug", "date", "target", "action", "company",
    "prescription", "act", "user", "fee", "priority", "review",
    # Regulatory application types — these get captured by DRUG(ABBR)
    # regex for patterns like "Application (BLA)" or "License (NDA)".
    "application", "license", "new", "supplemental", "submission",
    "nda", "bla", "snda", "sbla", "ind", "abla", "anda",
    # Filing labels
    "ex", "form", "annex", "exhibit", "document", "filing", "press", "release",
    # Generic leaders
    "the", "a", "an", "its", "our", "their", "this", "these",
    "announces", "announced", "announcement", "receives", "reports", "granted",
    "on", "track", "under", "with", "for", "of", "from", "to", "in",
    # Qualitative / study descriptors that LOOK like lowercase INNs
    "positive", "negative", "mixed", "topline", "phase", "initial",
    "pivotal", "interim", "ongoing", "preliminary", "clinical", "final",
    "recent", "updated", "successful", "additional", "further", "previous",
    "primary", "secondary", "tertiary", "first", "second", "third",
    "patient", "patients", "subject", "subjects", "participant", "participants",
    "safety", "efficacy", "tolerability", "pharmacokinetic", "pharmacodynamic",
    "endpoint", "endpoints", "cohort", "cohorts", "arm", "arms",
    "randomized", "controlled", "blinded", "crossover", "single", "double",
    "treatment", "placebo", "standard", "care", "disease", "condition",
}


# Common INN suffixes that confirm a lowercase word is probably a drug
# name. Not a hard requirement but used to reject weak candidates.
_INN_SUFFIXES = (
    "mab", "nib", "ib", "ide", "ate", "one", "ol", "xat", "tan", "sartan",
    "pril", "statin", "tinib", "ciclib", "ciclax", "ciclox", "ergoline",
    "azepam", "idine", "orib", "parib", "gliptin", "sen", "rsen", "erin",
    "vastatin", "stin", "zumab", "tuzumab", "ciclib", "stat", "vir",
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


def _extract_drug_name(body: str, headline: str | None = None) -> str | None:
    """Best-effort drug name extraction.

    Biotech press releases show three common forms near a PDUFA mention:
      A. Drug as subject of the sentence containing the PDUFA mention:
         "Veligrotug on Track with a PDUFA Target Action Date of June 30, 2026"
      B. Drug + parenthetical abbreviation before the PDUFA mention:
         "Oxylanthanum carbonate (OLC) New Drug Application (NDA)
          resubmission ... with a PDUFA target action date of June 29, 2026"
      C. Drug in the prior sentence (with NDA/BLA/sBLA/sNDA keyword):
         "zilganersen in Alexander disease ... PDUFA date set for Sep 22"

    Strategy — try in order:
      1. DRUG + (ABBR) capture in the 800-char window.
      2. DRUG as first word of the sentence containing the PDUFA mention.
      3. DRUG referenced in the same sentence via 'for X', 'of X'.
      4. Fall back to the first capitalized token near NDA/BLA keywords.
    """
    if not body:
        return None

    # Find the first PDUFA-ish mention. Use "pdufa" OR "target action" so we
    # catch 'Veligrotug on Track with a PDUFA Target Action Date of...' even
    # when the exact word "pdufa" comes later.
    lower = body.lower()
    idx = lower.find("pdufa")
    if idx < 0:
        idx = lower.find("target action date")
    if idx < 0:
        idx = lower.find("fda action")
    if idx < 0:
        return None

    # Window: 600 chars before + 300 after the mention.
    window = body[max(0, idx - 600) : idx + 300]

    def _clean(s: str) -> str | None:
        s = re.sub(r"\s+", " ", s).strip().strip(".,;:()")
        if not s:
            return None
        first = s.split()[0].lower().strip(".,;:")
        if first in _DRUG_BLACKLIST:
            return None
        # Reject EX-99-style filing labels ("EX-99", "EX-99.1", "EX-21", etc.)
        if re.match(r"^EX[-.\s]?\d", s, re.IGNORECASE):
            return None
        return s[:100]

    # (1) DRUG (ABBR): "Oxylanthanum carbonate (OLC)"
    # Skip matches where the inner word is a regulatory application type
    # ("Application (BLA)" / "License (NDA)" etc. — those are not drug names).
    for m in re.finditer(
        r"\b([A-Z][a-z]+(?:\s+[a-z]+){0,2})\s*\(([A-Z]{2,6})\)",
        window,
    ):
        candidate = m.group(1).strip()
        first_word = candidate.split()[0].lower()
        # All-words-blacklisted check: if every lowercase word in the
        # candidate is boilerplate, skip.
        words = candidate.lower().split()
        if all(w in _DRUG_BLACKLIST for w in words):
            continue
        if first_word in _DRUG_BLACKLIST:
            continue
        name = _clean(candidate)
        if name:
            return f"{name} ({m.group(2)})"

    # (2) DRUG as first word of sentence containing PDUFA/target-action.
    # Split window into sentences, find the one with the mention, take the
    # first capitalized non-blacklisted token.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", window)
    for s in sentences:
        if re.search(r"pdufa|target\s+action|fda\s+action", s, re.IGNORECASE):
            # Find first capitalized word in the sentence
            m = re.search(
                r"\b([A-Z][a-z]{2,}(?:[a-z0-9\-]+)?)\b", s
            )
            if m:
                name = _clean(m.group(1))
                if name:
                    return name
            break

    # (3) "for <DRUG>" with drug NOT being a month (blacklist enforced).
    for pattern in (_DRUG_MENTION_BEFORE, _DRUG_MENTION_APP):
        m = pattern.search(window)
        if m:
            name = _clean(m.group(1))
            if name:
                return name

    # (4) Headline fallback
    if headline and not headline.lower().startswith("ex-"):
        h = re.sub(r"^(Announces|Receives|Reports|Provides)\s+", "", headline, flags=re.IGNORECASE)
        m = re.match(r"^([A-Z][A-Za-z0-9\-]{2,30}(?:®|™|\*)?)", h)
        if m:
            name = _clean(m.group(1))
            if name:
                return name

    # (5) Lowercase INN fallback. Drug names often follow these cues:
    #   "study of <drug>"  |  "dose of <drug>"  |  "trial of <drug>"
    #   "treatment with <drug>"  |  "for <drug> in <disease>"
    # We only accept the word IMMEDIATELY after the cue and require either
    # a recognized INN suffix OR an adjacent drug-class keyword. This
    # avoids capturing generic study descriptors like "pivotal" / "interim".
    patterns = [
        # Cue → drug; enforce "of" only (not "from/with") to reduce false
        # positives like "data from <adjective> study".
        r"(?:study|trial|efficacy|treatment|dose|program)\s+of\s+([a-z]{5,25}(?:-[a-z0-9]+)?)\b",
        r"(?:treatment|dosed?)\s+with\s+([a-z]{5,25}(?:-[a-z0-9]+)?)\b",
        r"\bfor\s+([a-z]{5,25}(?:-[a-z0-9]+)?)\s+in\s+(?:patients|[a-z]+\s+(?:disease|syndrome))",
    ]
    for pat in patterns:
        for m in re.finditer(pat, window, re.IGNORECASE):
            candidate = m.group(1).strip().lower()
            if candidate in _DRUG_BLACKLIST:
                continue
            # Require either a known INN suffix or >= 8 letters (long
            # biotech code names like "venglustat" / "zilganersen").
            if candidate.endswith(_INN_SUFFIXES) or len(candidate) >= 8:
                return candidate

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
                drug_name = _extract_drug_name(body, headline=pr[3]) or "Unspecified"
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
