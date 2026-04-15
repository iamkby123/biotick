"""
Match trial sponsors to companies using exact and fuzzy matching.

Runs after bulk trial import to link orphaned trials to their parent companies
and auto-create drug entries from trial interventions.
"""

import asyncio
import logging
import re
from datetime import datetime

from rapidfuzz import fuzz, process
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.company import Company, SponsorAlias
from app.models.trial import Trial
from app.models.drug import Drug
from app.models.sync_log import SyncLog
from app.config import BIOTECH_SIC_CODES
from app.sync.trial_sync import _extract_interventions, _classify_therapeutic_area, PHASE_RANK

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 82


def _normalize_name(name: str) -> str:
    """Normalize a company/sponsor name for matching."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [", inc.", ", inc", " inc.", " inc", ", ltd.", ", ltd", " ltd.",
                   " ltd", " plc", " corp.", " corp", " co.", " co",
                   " corporation", " limited", " gmbh", " ag", " sa", " nv",
                   " se", " a/s", " a.s.", " oy"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    # Remove punctuation
    name = re.sub(r"[^\w\s]", "", name)
    return name.strip()


def _slugify(name: str) -> str:
    """Create a URL-safe slug from a drug name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")[:200]


async def match_sponsors(db: AsyncSession) -> int:
    """
    Match trial sponsors to companies.
    Returns number of trials matched.
    """
    log = SyncLog(
        sync_type="SPONSOR_MATCH",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Load all biotech company aliases into memory
        result = await db.execute(
            select(SponsorAlias, Company.name).join(
                Company, SponsorAlias.ticker == Company.ticker
            ).where(Company.sic_code.in_(BIOTECH_SIC_CODES))
        )
        rows = result.all()

        # Build lookup: normalized_name -> ticker
        alias_to_ticker: dict[str, str] = {}
        all_aliases: list[str] = []
        alias_raw_to_ticker: dict[str, str] = {}

        for alias, company_name in rows:
            norm = _normalize_name(alias.alias_name)
            alias_to_ticker[norm] = alias.ticker
            alias_raw_to_ticker[alias.alias_name.lower()] = alias.ticker
            all_aliases.append(norm)

            # Also add the company name
            norm_name = _normalize_name(company_name)
            if norm_name not in alias_to_ticker:
                alias_to_ticker[norm_name] = alias.ticker
                all_aliases.append(norm_name)

        logger.info(f"Loaded {len(all_aliases)} aliases for {len(set(alias_to_ticker.values()))} companies")

        if not all_aliases:
            log.completed_at = datetime.utcnow()
            log.status = "COMPLETED"
            log.records_processed = 0
            await db.commit()
            return 0

        # Get all unmatched trials
        total_unmatched = (await db.execute(
            select(func.count()).where(Trial.company_ticker.is_(None))
        )).scalar() or 0

        logger.info(f"Found {total_unmatched} unmatched trials")

        matched = 0
        batch_size = 500
        offset = 0

        while offset < total_unmatched:
            result = await db.execute(
                select(Trial)
                .where(Trial.company_ticker.is_(None))
                .limit(batch_size)
            )
            trials = result.scalars().all()

            if not trials:
                break

            for trial in trials:
                sponsor = trial.sponsor_name
                if not sponsor:
                    continue

                # Try exact match first
                norm_sponsor = _normalize_name(sponsor)
                ticker = alias_to_ticker.get(norm_sponsor)

                # Try raw lowercase match
                if not ticker:
                    ticker = alias_raw_to_ticker.get(sponsor.lower())

                # Fall back to fuzzy match
                if not ticker and all_aliases:
                    match = process.extractOne(
                        norm_sponsor,
                        all_aliases,
                        scorer=fuzz.token_sort_ratio,
                        score_cutoff=FUZZY_THRESHOLD,
                    )
                    if match:
                        matched_name, score, _ = match
                        ticker = alias_to_ticker.get(matched_name)

                if ticker:
                    trial.company_ticker = ticker
                    matched += 1

            await db.commit()
            offset += batch_size
            logger.info(f"Sponsor matching progress: {matched} matched so far")

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = matched
        await db.commit()

        logger.info(f"Sponsor matching complete: {matched}/{total_unmatched} trials matched")
        return matched

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Sponsor matching failed: {e}")
        raise
