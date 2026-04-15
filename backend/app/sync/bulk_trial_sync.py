"""
Bulk download all interventional drug/biologic trials from ClinicalTrials.gov.

Instead of per-company queries, downloads ALL trials and links them to companies
via sponsor matching afterward.
"""

import asyncio
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import requests as req_lib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_upsert

from app.models.trial import Trial
from app.models.sync_log import SyncLog
from app.config import CT_GOV_BASE_URL
from app.sync.trial_sync import (
    _parse_date,
    _extract_interventions,
    _classify_therapeutic_area,
    PHASE_MAP,
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)

# Session for requests (ClinicalTrials.gov blocks httpx)
_session = req_lib.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})


def _fetch_page(page_token: str | None = None) -> dict:
    """Fetch one page of trials from ClinicalTrials.gov (blocking)."""
    params = {
        "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
        "pageSize": 1000,
    }
    if page_token:
        params["pageToken"] = page_token
    resp = _session.get(f"{CT_GOV_BASE_URL}/studies", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


async def bulk_download_trials(db: AsyncSession) -> int:
    """
    Mass download all interventional trials from ClinicalTrials.gov.
    Returns total number of trials synced.
    """
    log = SyncLog(
        sync_type="BULK_TRIALS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        loop = asyncio.get_event_loop()
        total_count = 0
        page_num = 0
        next_token = None

        while True:
            page_num += 1

            # Fetch page in thread pool
            try:
                data = await loop.run_in_executor(
                    _executor, _fetch_page, next_token
                )
            except Exception as e:
                if "429" in str(e) or "Too Many" in str(e):
                    logger.warning("Rate limited, waiting 60s...")
                    await asyncio.sleep(60)
                    data = await loop.run_in_executor(
                        _executor, _fetch_page, next_token
                    )
                else:
                    logger.error(f"Error fetching page {page_num}: {e}")
                    break

            studies = data.get("studies", [])
            if not studies:
                break

            # Process studies
            page_count = 0
            for study in studies:
                try:
                    protocol = study.get("protocolSection", {})
                    id_module = protocol.get("identificationModule", {})
                    status_module = protocol.get("statusModule", {})
                    design_module = protocol.get("designModule", {})
                    desc_module = protocol.get("descriptionModule", {})
                    conditions_module = protocol.get("conditionsModule", {})
                    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

                    nct_id = id_module.get("nctId")
                    if not nct_id:
                        continue

                    # Phase
                    phases = design_module.get("phases", [])
                    raw_phase = phases[-1] if phases else None
                    phase = PHASE_MAP.get(raw_phase, raw_phase)

                    # Conditions
                    conditions = conditions_module.get("conditions", [])
                    indication = conditions[0] if conditions else None
                    therapeutic_area = _classify_therapeutic_area(indication) if indication else None

                    # Sponsor
                    lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "Unknown")

                    # Dates
                    start_date = _parse_date(status_module.get("startDateStruct", {}).get("date"))
                    primary_completion = _parse_date(status_module.get("primaryCompletionDateStruct", {}).get("date"))
                    completion = _parse_date(status_module.get("completionDateStruct", {}).get("date"))
                    results_posted = _parse_date(status_module.get("resultsFirstPostDateStruct", {}).get("date"))
                    last_update = _parse_date(status_module.get("lastUpdatePostDateStruct", {}).get("date"))

                    # Enrollment
                    enrollment = design_module.get("enrollmentInfo", {}).get("count")

                    # Upsert trial — do NOT set company_ticker or drug_id
                    # Those get linked by sponsor_matcher afterward
                    stmt = pg_upsert(Trial).values(
                        nct_id=nct_id,
                        sponsor_name=lead_sponsor,
                        title=id_module.get("officialTitle") or id_module.get("briefTitle", "Unknown"),
                        brief_summary=(desc_module.get("briefSummary", "") or "")[:5000],
                        phase=phase,
                        overall_status=status_module.get("overallStatus"),
                        therapeutic_area=therapeutic_area,
                        indication=indication,
                        enrollment=enrollment,
                        start_date=start_date,
                        primary_completion_date=primary_completion,
                        completion_date=completion,
                        study_type=design_module.get("studyType"),
                        results_first_posted=results_posted,
                        last_update_posted=last_update,
                        updated_at=datetime.utcnow(),
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["nct_id"],
                        set_={
                            "phase": stmt.excluded.phase,
                            "overall_status": stmt.excluded.overall_status,
                            "enrollment": stmt.excluded.enrollment,
                            "primary_completion_date": stmt.excluded.primary_completion_date,
                            "completion_date": stmt.excluded.completion_date,
                            "therapeutic_area": stmt.excluded.therapeutic_area,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await db.execute(stmt)
                    page_count += 1

                except Exception as e:
                    continue

            total_count += page_count
            await db.commit()

            logger.info(f"Bulk trial import page {page_num}: {page_count} trials (total: {total_count})")

            # Check for next page
            next_token = data.get("nextPageToken")
            if not next_token:
                break

            # Rate limit
            await asyncio.sleep(1.5)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_count
        await db.commit()

        logger.info(f"Bulk trial import complete: {total_count} trials")
        return total_count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Bulk trial import failed: {e}")
        raise
