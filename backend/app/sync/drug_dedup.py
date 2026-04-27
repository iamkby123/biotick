"""Deduplicate drug rows produced by ClinicalTrials.gov sponsor matching.

The sponsor-matcher walks every CT.gov trial and creates a `drugs` row
per distinct intervention name. Sponsors register the same molecule
under many label variants:

    Aflibercept
    Aflibercept (AVE0005)
    Aflibercept (ziv-aflibercept, AVE0005, VEGF trap, ZALTRAP®)
    Alemtuzumab
    Alemtuzumab GZ402673
    Alemtuzumab plus Fludarabine
    ALX-0171
    ALX-0171 3.0 mg/kg

Result: Sanofi shows 308 "drugs" instead of ~80.

This pass:
  1. Computes a normalized name for every drug (strip parens, dose,
     combo suffixes, trailing dev codes).
  2. Groups by (company_ticker, normalized_name).
  3. For each group with >1 row picks a canonical: shortest name first,
     then row with highest_phase populated, then oldest created_at.
  4. Re-points trials.drug_id and catalysts.drug_id to canonical.
  5. Deletes duplicate drug rows.

Idempotent: re-runs that find no dupes do nothing.
"""

import logging
import re
from datetime import datetime
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


# ─── Normalizer ─────────────────────────────────────────────────────────


# Match "(... anything ...)" — strip parenthetical aliases / codes.
_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")

# Dose annotations: "3.0 mg/kg", "100 mcg", "10 mg/day", "(0.5-mL dose)".
_DOSE_RE = re.compile(
    r"\s*[,;]?\s*\d+(?:[.,]\d+)?\s*"
    r"(?:mg|mcg|kg|µg|ug|iu|units?|ml|g|u)\b"
    r"(?:/(?:kg|day|week|hr|hour|ml|m\^?2))?\s*\d*.*$",
    re.IGNORECASE,
)

# Vaccine-formulation noise: "2016-2017 formulation", "No Preservative",
# "(0.5-mL dose)", "USP Trivalent Types A and B", "high-dose".
_VACCINE_NOISE_RE = re.compile(
    r"\s*[,;]?\s*"
    r"(?:"
    r"\d{4}[-–]\d{4}\s*formulation"
    r"|\bno\s+preservative\b"
    r"|\bhigh[-\s]?dose\b"
    r"|\busp\b\s+(?:trivalent|quadrivalent)\s+types?\s+[a-z]+(?:\s+and\s+[a-z]+)?"
    r")"
    r".*$",
    re.IGNORECASE,
)

# Combo separators — "plus X", "with X", "+X", "and X" (only as a clear
# word boundary so "ChimeriVax-JE" doesn't get cut at the dash).
_COMBO_RE = re.compile(
    r"\s+(plus|with|and|\+)\s+.+$",
    re.IGNORECASE,
)

# Trailing dev / sponsor code (Sanofi SAR, Regeneron REGN, Lilly LY, Merck
# MK, BMS, Pfizer PF, GSK, AstraZeneca AZD, Genzyme GZ, Biogen BIIB, JNJ,
# Novartis NVS, Roche RG, Moderna MRT, Kadmon KD).
_DEV_CODE_RE = re.compile(
    r"\s+(SAR|REGN|GZ|MK|LY|BMS|PF|GSK|AZD|RG|BIIB|JNJ|NVS|MRT|KD|PRA|JTX|VX)"
    r"[-\s]?\d{2,8}\b",
    re.IGNORECASE,
)

# Salt-form / counter-ion suffixes — "mesylate", "succinate", "hydrochloride".
# Only strip if the resulting trimmed name still has at least one word.
_SALT_FORM_RE = re.compile(
    r"\s+(?:"
    r"hydrochloride|sulfate|sulphate|sodium|potassium|"
    r"mesylate|maleate|fumarate|tartrate|citrate|"
    r"succinate|acetate|phosphate|hydrobromide|"
    r"hcl|hbr|na|k"
    r")\s*(?:\([^)]*\))?\s*$",
    re.IGNORECASE,
)

# Route of administration — " IV", "intravenous", "PO", "oral", "SC".
# Only strip when at end-of-string and preceded by whitespace.
_ROUTE_RE = re.compile(
    r"\s+(?:IV|IM|SC|SQ|PO|IT|PR|"
    r"intravenous|intramuscular|subcutaneous|oral|inhaled|"
    r"intranasal|intrathecal|intravitreal|topical|"
    r"injection|auto[-\s]?injector|infusion|"
    r"pre[-\s]?filled\s+syringe|syringe)\b\.?$",
    re.IGNORECASE,
)

# Trailing "vaccine" / "tablet" / "capsule" suffix when there's already
# substance to the name (so "vaccine" alone isn't normalized to empty).
_TRAILING_DOSE_FORM_RE = re.compile(
    r"\s+(?:vaccine|tablet|capsule|injection)\.?$",
    re.IGNORECASE,
)

# Whitespace + trailing-punct normalizers.
_WS_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s,;:.®™*]+$")


def normalize_drug_name(name: str | None) -> str:
    """Normalize a drug name to a stable canonical key for dedup.

    Order matters — we peel suffixes from outside-in: parens first
    (dosage codes), then dose, vaccine-formulation noise, combo
    suffixes, dev codes, salt forms, route, and finally bare
    "vaccine" / "tablet" markers.
    """
    if not name:
        return ""
    s = name.lower().strip()

    # Strip all parenthetical content (run repeatedly for nested parens)
    while True:
        s2 = _PAREN_RE.sub(" ", s)
        if s2 == s:
            break
        s = s2

    # Vaccine-formulation noise: "2016-2017 formulation", "No Preservative"
    s = _VACCINE_NOISE_RE.sub("", s)

    # Dose suffix
    s = _DOSE_RE.sub("", s)

    # Combo suffix
    s = _COMBO_RE.sub("", s)

    # Trailing dev code (e.g. " SAR236553", " GZ402673")
    s = _DEV_CODE_RE.sub("", s)

    # Salt form (only if substance remains afterwards)
    candidate = _SALT_FORM_RE.sub("", s)
    if candidate.strip() and candidate.strip() != "":
        s = candidate

    # Administration route
    s = _ROUTE_RE.sub("", s)

    # Trailing dose-form word (only if there's a real name first)
    candidate = _TRAILING_DOSE_FORM_RE.sub("", s)
    if candidate.strip() and len(candidate.strip().split()) >= 1:
        s = candidate

    # Strip lingering trademark / brand markers + trailing punctuation
    s = _TRAILING_PUNCT_RE.sub("", s)

    # Collapse whitespace
    s = _WS_RE.sub(" ", s).strip()
    return s


# ─── Dedup runner ───────────────────────────────────────────────────────


def _pick_canonical(rows: list[tuple]) -> tuple:
    """Given a list of (drug_id, drug_name, highest_phase, created_at) tuples
    that all normalize to the same key, return the canonical row.

    Preference order:
      1. Shortest drug_name (likely the INN by itself, e.g. "Aflibercept"
         beats "Aflibercept (ziv-aflibercept, AVE0005, ...)")
      2. drug_class / highest_phase populated (more enriched record)
      3. Oldest created_at (more stable identifier; trials reference older IDs)
    """
    def sort_key(r):
        drug_id, drug_name, highest_phase, created_at = r
        return (
            len(drug_name or ""),
            0 if highest_phase else 1,
            created_at,
        )

    return sorted(rows, key=sort_key)[0]


async def dedupe_company(
    db: AsyncSession,
    ticker: str,
) -> tuple[int, int]:
    """Dedupe one company's drugs. Returns (groups_merged, rows_deleted)."""
    rows = (await db.execute(
        text(
            "SELECT drug_id, drug_name, highest_phase, created_at "
            "FROM drugs WHERE company_ticker = :t"
        ),
        {"t": ticker},
    )).fetchall()

    # Group by normalized name
    groups: dict[str, list] = {}
    for r in rows:
        key = normalize_drug_name(r[1])
        if not key:
            continue
        groups.setdefault(key, []).append(r)

    groups_merged = 0
    rows_deleted = 0

    for norm_key, group in groups.items():
        if len(group) <= 1:
            continue

        canonical = _pick_canonical(group)
        canonical_id = canonical[0]
        dupe_ids = [r[0] for r in group if r[0] != canonical_id]
        if not dupe_ids:
            continue

        # Re-point all child references first, THEN delete the dupes.
        # Trials reference drug_id; catalysts reference drug_id.
        await db.execute(
            text("UPDATE trials SET drug_id = :canonical WHERE drug_id = ANY(:dupes)"),
            {"canonical": canonical_id, "dupes": dupe_ids},
        )
        await db.execute(
            text("UPDATE catalysts SET drug_id = :canonical WHERE drug_id = ANY(:dupes)"),
            {"canonical": canonical_id, "dupes": dupe_ids},
        )
        result = await db.execute(
            text("DELETE FROM drugs WHERE drug_id = ANY(:dupes) RETURNING drug_id"),
            {"dupes": dupe_ids},
        )
        rows_deleted += len(result.fetchall())
        groups_merged += 1
        logger.debug(
            f"  {ticker}: merged {len(dupe_ids)} into '{canonical[1]}' "
            f"(norm='{norm_key}')"
        )

    await db.commit()
    return groups_merged, rows_deleted


async def sync_drug_dedup(
    db: AsyncSession,
    tickers: Iterable[str] | None = None,
) -> dict[str, int]:
    """Run dedup across all companies (or a specified list)."""
    log = SyncLog(
        sync_type="DRUG_DEDUP",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        if tickers is not None:
            ticker_list = list(tickers)
        else:
            ticker_list = [
                t for (t,) in (await db.execute(
                    text("SELECT DISTINCT company_ticker FROM drugs ORDER BY 1")
                )).fetchall()
            ]
        logger.info(f"drug_dedup: scanning {len(ticker_list)} companies")

        total_merged = 0
        total_deleted = 0
        biggest_winners: list[tuple[str, int]] = []

        for tk in ticker_list:
            try:
                merged, deleted = await dedupe_company(db, tk)
                total_merged += merged
                total_deleted += deleted
                if deleted >= 10:
                    biggest_winners.append((tk, deleted))
            except Exception as e:
                logger.warning(f"drug_dedup {tk}: {e}")
                continue

        biggest_winners.sort(key=lambda x: -x[1])

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_deleted
        log.error_message = (
            f"merged_groups={total_merged} rows_deleted={total_deleted} "
            f"top_winners={biggest_winners[:10]}"
        )[:2000]
        await db.commit()
        logger.info(
            f"drug_dedup done: {total_merged} groups merged, "
            f"{total_deleted} rows deleted across {len(ticker_list)} companies"
        )
        return {
            "groups_merged": total_merged,
            "rows_deleted": total_deleted,
            "companies_scanned": len(ticker_list),
            "biggest_winners": biggest_winners[:10],
        }

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"drug_dedup failed: {e}")
        raise
