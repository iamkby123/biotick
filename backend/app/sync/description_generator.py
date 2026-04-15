"""
Auto-generate company descriptions from pipeline and trial data.

Creates a short, informative description for each company based on
their drug pipeline, therapeutic areas, and clinical stage.
"""

import logging
from datetime import datetime
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.company import Company
from app.models.drug import Drug
from app.models.trial import Trial
from app.models.sync_log import SyncLog
from app.config import BIOTECH_SIC_CODES

logger = logging.getLogger(__name__)

SIC_DESCRIPTIONS = {
    "2833": "pharmaceutical",
    "2834": "pharmaceutical",
    "2835": "diagnostic",
    "2836": "biotechnology",
    "3841": "medical device",
    "3826": "laboratory instruments",
    "2860": "specialty chemical",
    "8731": "life sciences research",
}


async def generate_descriptions(db: AsyncSession) -> int:
    """Generate descriptions for companies missing them."""
    log = SyncLog(
        sync_type="DESCRIPTIONS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        result = await db.execute(
            select(Company).where(
                Company.sic_code.in_(BIOTECH_SIC_CODES),
                Company.description.is_(None),
            )
        )
        companies = result.scalars().all()
        count = 0

        for company in companies:
            # Get pipeline data
            drugs_result = await db.execute(
                select(Drug).where(Drug.company_ticker == company.ticker)
            )
            drugs = drugs_result.scalars().all()

            # Get trial count
            trial_count_result = await db.execute(
                select(func.count()).where(Trial.company_ticker == company.ticker)
            )
            trial_count = trial_count_result.scalar() or 0

            # Build description
            desc = _build_description(company, drugs, trial_count)
            if desc:
                company.description = desc

                # Also set therapeutic_area from pipeline
                if not company.therapeutic_area and drugs:
                    areas = Counter(d.therapeutic_area for d in drugs if d.therapeutic_area)
                    if areas:
                        company.therapeutic_area = areas.most_common(1)[0][0]

                count += 1

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = count
        await db.commit()

        logger.info(f"Generated {count} company descriptions")
        return count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Description generation failed: {e}")
        raise


def _build_description(company: Company, drugs: list, trial_count: int) -> str:
    """Build a description from available data."""
    parts = []

    # Company type
    sic_type = SIC_DESCRIPTIONS.get(company.sic_code, "biopharmaceutical")
    name = company.name.rstrip("., ")

    # Location
    location = ""
    if company.city and company.state:
        location = f" headquartered in {company.city}, {company.state}"
    elif company.city and company.country:
        location = f" headquartered in {company.city}, {company.country}"

    # Pipeline summary
    if drugs:
        # Therapeutic areas
        areas = Counter(d.therapeutic_area for d in drugs if d.therapeutic_area and d.therapeutic_area != "Other")
        top_areas = [a for a, _ in areas.most_common(3)]

        # Phase breakdown
        phases = Counter(d.highest_phase for d in drugs if d.highest_phase)
        phase_parts = []
        for p in ["PHASE3", "PHASE2", "PHASE1", "PHASE4"]:
            if phases.get(p):
                label = p.replace("PHASE", "Phase ")
                phase_parts.append(f"{phases[p]} in {label}")

        # Lead drug
        lead_drugs = sorted(
            [d for d in drugs if d.highest_phase in ("PHASE3", "PHASE4")],
            key=lambda d: {"PHASE4": 4, "PHASE3": 3}.get(d.highest_phase or "", 0),
            reverse=True,
        )

        # Build sentence
        parts.append(f"{name} is a {sic_type} company{location}.")

        if top_areas:
            area_str = ", ".join(top_areas[:2])
            parts.append(f"The company focuses on {area_str}.")

        if len(drugs) > 0:
            pipeline_str = f"It has {len(drugs)} drug programs"
            if phase_parts:
                pipeline_str += f" ({', '.join(phase_parts[:3])})"
            pipeline_str += f" across {trial_count} clinical trials." if trial_count > 0 else "."
            parts.append(pipeline_str)

        if lead_drugs:
            lead = lead_drugs[0]
            indication = f" for {lead.indication}" if lead.indication else ""
            parts.append(
                f"Lead program: {lead.drug_name}{indication}."
            )
    else:
        parts.append(f"{name} is a {sic_type} company{location}.")
        if trial_count > 0:
            parts.append(f"The company is involved in {trial_count} clinical trials.")

    return " ".join(parts)
