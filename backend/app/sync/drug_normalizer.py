"""
Normalize drug names by stripping dosages, frequencies, routes, and other noise.

Cleans up entries like:
  "Gabapentin 100mg" → "Gabapentin"
  "2-weeks placebo then gabapentin" → "Gabapentin"
  "ACE-031 0.5 mg/kg q4wk" → "ACE-031"
"""

import re
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.drug import Drug
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

# Patterns to strip from drug names
DOSAGE_PATTERNS = [
    r'\s+\d+[\./]?\d*\s*(mg|mcg|ug|g|ml|µg|IU|units?|mmol)\b.*',  # "100mg..."
    r'\s+\d+\s*mg/kg\b.*',  # "0.5 mg/kg..."
    r'\s*\(?\d+\s*(mg|mcg|ml|g)\)?',  # "(100mg)"
    r'\s+q\d+\s*w(k|eek)s?\b.*',  # "q4wk"
    r'\s+\d+x\s*daily\b.*',  # "2x daily"
    r'\s+(once|twice|three times)\s+(daily|weekly|monthly)\b.*',  # "once daily"
    r'\s+po\b.*',  # "po" (oral)
    r'\s+bid\b.*',  # "bid"
    r'\s+tid\b.*',  # "tid"
    r'\s+qd\b.*',  # "qd"
    r'\s+iv\b.*',  # "iv"
    r'\s+sc\b.*',  # "sc" (subcutaneous)
    r'\s+im\b.*',  # "im" (intramuscular)
]

# Names that aren't real drugs
SKIP_NAMES = {
    "placebo", "sham", "standard of care", "standard care", "observation",
    "no treatment", "no intervention", "control", "usual care",
    "best supportive care", "active control", "comparator",
    "treatment as usual", "waitlist", "wait list",
}

# Prefix patterns to remove
PREFIX_PATTERNS = [
    r'^\d+[-\s]*weeks?\s+',  # "2-weeks "
    r'^\d+[-\s]*months?\s+',  # "3-months "
    r'^(then|followed by|plus|and|or|with)\s+',  # "then gabapentin"
]


def normalize_drug_name(name: str) -> str:
    """Clean up a drug name."""
    if not name:
        return name

    original = name

    # Strip prefix patterns
    for pattern in PREFIX_PATTERNS:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    # Strip dosage patterns
    for pattern in DOSAGE_PATTERNS:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    # Remove trailing parenthetical dosages
    name = re.sub(r'\s*\([^)]*\d+\s*(mg|mcg|ml|g|IU)[^)]*\)\s*$', '', name, flags=re.IGNORECASE)

    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Remove trailing commas, periods, hyphens
    name = name.rstrip(' ,-.')

    # If we stripped everything, keep original
    if not name or len(name) < 2:
        return original

    return name


def is_placebo(name: str) -> bool:
    """Check if a drug name is actually a placebo/control."""
    return name.lower().strip() in SKIP_NAMES or name.lower().startswith("placebo")


async def normalize_all_drugs(db: AsyncSession) -> int:
    """Clean up all drug names in the database."""
    log = SyncLog(
        sync_type="DRUG_NORMALIZE",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        result = await db.execute(select(Drug))
        drugs = result.scalars().all()

        cleaned = 0
        removed = 0

        for drug in drugs:
            # Check if it's a placebo
            if is_placebo(drug.drug_name):
                # Mark as inactive instead of deleting
                drug.status = "PLACEBO"
                removed += 1
                continue

            # Normalize the name
            new_name = normalize_drug_name(drug.drug_name)
            if new_name != drug.drug_name:
                drug.drug_name = new_name
                cleaned += 1

        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = cleaned + removed
        await db.commit()

        logger.info(f"Drug normalization: {cleaned} cleaned, {removed} marked as placebo")
        return cleaned + removed

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Drug normalization failed: {e}")
        raise
