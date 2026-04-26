"""Daily data-quality audit job.

Cross-references our database against authoritative sources and flags rows
that look wrong. Writes one consolidated row per run to `sync_log` with the
findings as a JSON-stringified `error_message` so admins can monitor drift.

What it checks:
1. **Catalysts** — auto-flip stale `is_past=false` rows whose `expected_date`
   is more than 14 days past today. (Mirrors the cross-ref we already do in
   fda_calendar_sync, kept here as a belt-and-suspenders.)
2. **Drug names** — count rows with title-cased dose suffixes ("0.4Mg", "100 G")
   so we can tell when ClinicalTrials.gov sends us mangled brand names.
3. **Insider trades** — count rows where the filing came >180 days after the
   trade (legitimately allowed but worth tracking).
4. **Short interest** — count rows where total_volume is null/0 (FINRA
   sometimes publishes empty rows for halted tickers).
5. **PDUFA catalysts** — count rows extracted from press releases where the
   drug name fell back to "Unspecified" (extractor needs improvement).
6. **NCT IDs** — sample 10 trials and confirm they still exist on
   ClinicalTrials.gov (catches retracted / withdrawn studies we still show).

Each check produces a count + auto-fix where possible. The full result is
logged so we can see drift over time without spamming sync_log.
"""

import asyncio
import json
import logging
import random
from datetime import datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


_CT_GOV_API = "https://clinicaltrials.gov/api/v2/studies/{nct}?fields=protocolSection.identificationModule.briefTitle"


async def _check_nct_ids_live(client: httpx.AsyncClient, nct_ids: list[str]) -> int:
    """Probe a sample of NCT IDs against ClinicalTrials.gov v2 API. Returns
    the count of NCT IDs that returned 404."""
    missing = 0
    for nct in nct_ids:
        try:
            resp = await client.get(_CT_GOV_API.format(nct=nct), timeout=10)
            if resp.status_code == 404:
                missing += 1
            elif resp.status_code != 200:
                logger.debug(f"CT.gov {nct}: HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"CT.gov {nct}: {e}")
        await asyncio.sleep(0.2)  # be polite
    return missing


async def run_data_quality_audit(db: AsyncSession) -> dict:
    """Run all data-quality checks. Returns dict of findings + counts.

    Auto-fixes a few categories (stale catalyst is_past flag, obvious
    title-cased dose typos). Reports counts on the rest so admins can see
    if drift is accelerating.
    """
    log = SyncLog(
        sync_type="DATA_QUALITY_AUDIT",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    findings: dict = {}

    try:
        # 1. Auto-flip stale upcoming catalysts (>14 days past).
        flipped = (await db.execute(
            text("""
                UPDATE catalysts
                SET is_past = TRUE, updated_at = now()
                WHERE is_past = FALSE
                  AND expected_date < CURRENT_DATE - INTERVAL '14 days'
                RETURNING id
            """)
        )).fetchall()
        findings["catalysts_auto_flipped_past"] = len(flipped)

        # 2. Drug names with title-cased dose suffixes — auto-fix common patterns.
        # 'Mg' -> 'mg', 'Mcg' -> 'mcg', ' G$' (uppercase G as standalone unit) -> 'g'.
        fixed_drugs = (await db.execute(
            text(r"""
                UPDATE drugs
                SET drug_name = regexp_replace(
                                  regexp_replace(
                                    regexp_replace(drug_name, ' Mg$', ' mg', 'g'),
                                    ' Mcg$', ' mcg', 'g'),
                                  ' G$', ' g', 'g'
                                )
                WHERE drug_name ~ ' Mg$| Mcg$| G$| \d+ Mg | \d+ Mcg | \d+ G '
                RETURNING drug_id
            """)
        )).fetchall()
        findings["drug_names_dose_suffix_fixed"] = len(fixed_drugs)

        # 3. Insider trades filed >180 days late (informational; may indicate
        # late Form 4 amendments).
        late = (await db.execute(
            text("SELECT COUNT(*) FROM insider_trades WHERE (filing_date::date - transaction_date::date) > 180")
        )).scalar() or 0
        findings["insider_trades_filed_late_180d"] = int(late)

        # 4. Short-interest rows with no total volume.
        si_bad = (await db.execute(
            text("SELECT COUNT(*) FROM short_interest WHERE total_volume = 0 OR total_volume IS NULL")
        )).scalar() or 0
        findings["short_interest_zero_volume"] = int(si_bad)

        # 5. PDUFA catalysts with drug = 'Unspecified'.
        pdufa_unspec = (await db.execute(
            text("SELECT COUNT(*) FROM catalysts WHERE event_type='PDUFA' AND drug_name='Unspecified'")
        )).scalar() or 0
        findings["pdufa_unspecified_drug"] = int(pdufa_unspec)

        # 6. Press releases without AI summary that are >2 days old (gives
        # eight_k_pipeline a generous window to catch up).
        no_summary = (await db.execute(
            text("""
                SELECT COUNT(*) FROM press_releases
                WHERE summary IS NULL
                  AND filed_date < CURRENT_DATE - INTERVAL '2 days'
                  AND filed_date > CURRENT_DATE - INTERVAL '60 days'
            """)
        )).scalar() or 0
        findings["press_releases_no_summary_2d"] = int(no_summary)

        # 7. NCT ID liveness check — sample 10 random recent trials.
        nct_sample_rows = (await db.execute(
            text("""
                SELECT nct_id FROM trials
                WHERE nct_id IS NOT NULL
                  AND nct_id ~ '^NCT[0-9]{8}$'
                ORDER BY RANDOM()
                LIMIT 10
            """)
        )).fetchall()
        nct_ids = [r[0] for r in nct_sample_rows]
        try:
            async with httpx.AsyncClient() as client:
                missing = await _check_nct_ids_live(client, nct_ids)
            findings["ncts_sampled"] = len(nct_ids)
            findings["ncts_missing_404"] = missing
        except Exception as e:
            findings["nct_check_error"] = str(e)[:200]

        # 8. Catalyst total snapshot.
        cat_total = (await db.execute(
            text("SELECT COUNT(*) FROM catalysts WHERE is_past = false")
        )).scalar() or 0
        findings["catalysts_upcoming_total"] = int(cat_total)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = sum(
            v for v in findings.values() if isinstance(v, int)
        )
        log.error_message = json.dumps(findings)[:2000]
        await db.commit()
        logger.info(f"data_quality_audit findings: {findings}")
        return findings

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = (
            json.dumps({"error": str(e), "findings_so_far": findings})[:2000]
        )
        await db.commit()
        logger.error(f"data_quality_audit failed: {e}")
        raise
