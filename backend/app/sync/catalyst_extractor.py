"""
Extract catalysts from trial data.

Scans trials for upcoming completion dates and creates catalyst entries
with significance scoring based on phase, indication size, etc.
"""

import logging
from datetime import datetime, date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_upsert

from app.models.trial import Trial
from app.models.catalyst import Catalyst
from app.models.sync_log import SyncLog
from app.config import BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)

# Significance scoring by phase
PHASE_SIGNIFICANCE = {
    "PHASE3": 8,
    "PHASE4": 5,
    "PHASE2": 5,
    "PHASE1": 3,
}

# Bonus significance for high-value therapeutic areas
THERAPEUTIC_BONUS = {
    "Oncology": 1,
    "Rare Disease": 1,
    "Gene/Cell Therapy": 1,
}

# Trial statuses that indicate an upcoming catalyst
ACTIVE_STATUSES = {
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "ENROLLING_BY_INVITATION",
    "NOT_YET_RECRUITING",
}

# Completed status means results may be coming
COMPLETED_STATUSES = {
    "COMPLETED",
}


def _calculate_significance(
    phase: str | None,
    therapeutic_area: str | None,
    status: str | None,
) -> int:
    """Calculate significance score (1-10) for a catalyst."""
    base = PHASE_SIGNIFICANCE.get(phase, 2)
    bonus = THERAPEUTIC_BONUS.get(therapeutic_area, 0)

    # Completed trials get a bump — results are imminent
    if status in COMPLETED_STATUSES:
        bonus += 1

    return min(10, base + bonus)


def _determine_confidence(
    trial_status: str | None,
    has_primary_completion: bool,
    date_is_past: bool,
) -> str:
    """Determine confidence level for the catalyst date."""
    if trial_status in COMPLETED_STATUSES:
        return "HIGH"  # Trial is done, data readout expected
    if has_primary_completion and not date_is_past:
        return "MEDIUM"  # Has a future date from ClinicalTrials.gov
    return "LOW"  # Estimated or uncertain


async def extract_catalysts(db: AsyncSession) -> int:
    """
    Extract catalyst events from trial data.
    Returns the number of catalysts created/updated.
    """
    log = SyncLog(
        sync_type="CATALYSTS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        today = date.today()
        lookback = today - timedelta(days=30)  # Include recent past catalysts
        lookahead = today + timedelta(days=730)  # 2 years ahead

        count = 0

        # 1. Active trials with upcoming primary completion dates → DATA_READOUT catalysts
        result = await db.execute(
            select(Trial).where(
                and_(
                    Trial.company_ticker.isnot(None),
                    Trial.primary_completion_date.isnot(None),
                    Trial.primary_completion_date >= lookback,
                    Trial.primary_completion_date <= lookahead,
                    Trial.phase.in_(["PHASE1", "PHASE2", "PHASE3", "PHASE4"]),
                )
            )
        )
        trials_with_dates = result.scalars().all()

        for trial in trials_with_dates:
            is_past = trial.primary_completion_date < today

            significance = _calculate_significance(
                trial.phase, trial.therapeutic_area, trial.overall_status
            )
            confidence = _determine_confidence(
                trial.overall_status,
                True,
                is_past,
            )

            # Determine date precision
            date_precision = "MONTH"  # ClinicalTrials.gov dates are usually month-level

            # Build description
            phase_label = trial.phase.replace("PHASE", "Phase ") if trial.phase else "Unknown Phase"
            indication_str = f" for {trial.indication}" if trial.indication else ""
            drug_name = None
            if trial.drug_id:
                # Extract drug name from drug_id (format: ticker-drugname)
                parts = trial.drug_id.split("-", 1)
                drug_name = parts[1].replace("-", " ").title() if len(parts) > 1 else trial.drug_id

            description = f"{phase_label} data readout{indication_str}"

            # Upsert catalyst
            async with db.begin_nested():
                stmt = pg_upsert(Catalyst).values(
                    company_ticker=trial.company_ticker,
                    drug_id=trial.drug_id,
                    drug_name=drug_name,
                    event_type="DATA_READOUT",
                    event_description=description,
                    expected_date=trial.primary_completion_date,
                    date_precision=date_precision,
                    significance_score=significance,
                    confidence=confidence,
                    source="ClinicalTrials.gov",
                    source_url=f"https://clinicaltrials.gov/study/{trial.nct_id}",
                    is_past=is_past,
                    outcome="PENDING" if not is_past else None,
                    updated_at=datetime.utcnow(),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["company_ticker", "drug_name", "event_type", "expected_date"],
                    set_={
                        "significance_score": stmt.excluded.significance_score,
                        "confidence": stmt.excluded.confidence,
                        "is_past": stmt.excluded.is_past,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await db.execute(stmt)
            count += 1

        # 2. Recently completed trials without results → possible imminent DATA_READOUT
        result = await db.execute(
            select(Trial).where(
                and_(
                    Trial.company_ticker.isnot(None),
                    Trial.overall_status == "COMPLETED",
                    Trial.results_first_posted.is_(None),  # No results yet
                    Trial.phase.in_(["PHASE2", "PHASE3"]),
                    Trial.completion_date.isnot(None),
                    Trial.completion_date >= lookback,
                )
            )
        )
        completed_no_results = result.scalars().all()

        for trial in completed_no_results:
            significance = _calculate_significance(
                trial.phase, trial.therapeutic_area, "COMPLETED"
            )

            drug_name = None
            if trial.drug_id:
                parts = trial.drug_id.split("-", 1)
                drug_name = parts[1].replace("-", " ").title() if len(parts) > 1 else trial.drug_id

            phase_label = trial.phase.replace("PHASE", "Phase ") if trial.phase else ""
            description = f"{phase_label} completed — results pending"

            # Use completion_date + 3 months as estimated results date
            estimated_results = trial.completion_date + timedelta(days=90)

            async with db.begin_nested():
                stmt = pg_upsert(Catalyst).values(
                    company_ticker=trial.company_ticker,
                    drug_id=trial.drug_id,
                    drug_name=drug_name,
                    event_type="DATA_READOUT",
                    event_description=description,
                    expected_date=estimated_results,
                    date_precision="QUARTER",
                    significance_score=significance,
                    confidence="MEDIUM",
                    source="ClinicalTrials.gov (estimated)",
                    source_url=f"https://clinicaltrials.gov/study/{trial.nct_id}",
                    is_past=estimated_results < today,
                    outcome="PENDING",
                    updated_at=datetime.utcnow(),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["company_ticker", "drug_name", "event_type", "expected_date"],
                    set_={
                        "significance_score": stmt.excluded.significance_score,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await db.execute(stmt)
            count += 1

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Catalyst extraction complete: {count} catalysts created/updated")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Catalyst extraction failed: {e}")
        raise
