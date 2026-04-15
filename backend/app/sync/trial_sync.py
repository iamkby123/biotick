"""
Sync clinical trial data from ClinicalTrials.gov API v2.

For each biotech company, queries trials by sponsor name and upserts
into the trials table. Also auto-creates drug entries from trial interventions.
"""

import asyncio
import logging
import re
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor

import requests as req_lib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_upsert

from app.models.company import Company, SponsorAlias
from app.models.trial import Trial
from app.models.drug import Drug
from app.models.sync_log import SyncLog
from app.config import CT_GOV_BASE_URL, BIOTECH_SIC_CODES

_executor = ThreadPoolExecutor(max_workers=2)

# Session for requests (ClinicalTrials.gov blocks httpx)
_session = req_lib.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})

logger = logging.getLogger(__name__)

# Phase normalization map
PHASE_MAP = {
    "EARLY_PHASE1": "PHASE1",
    "PHASE1": "PHASE1",
    "PHASE2": "PHASE2",
    "PHASE3": "PHASE3",
    "PHASE4": "PHASE4",
    "NA": "NA",
}


def normalize_phases(phases: list[str]) -> str | None:
    """Normalize a list of phases from ClinicalTrials.gov into a single phase."""
    if not phases:
        return None
    # Handle combo phases: ["PHASE1", "PHASE2"] -> "PHASE2" (highest)
    mapped = [PHASE_MAP.get(p, p) for p in phases if PHASE_MAP.get(p, p) is not None]
    if not mapped:
        return None
    rank = {"PHASE4": 4, "PHASE3": 3, "PHASE2": 2, "PHASE1": 1, "NA": 0}
    return max(mapped, key=lambda p: rank.get(p, -1))

# Phase ranking for "highest phase" on drugs
PHASE_RANK = {
    "PHASE4": 5,
    "PHASE3": 4,
    "PHASE2": 3,
    "PHASE1": 2,
    "PRECLINICAL": 1,
}


def _parse_date(date_str: str | None) -> date | None:
    """Parse a date string from ClinicalTrials.gov (YYYY-MM-DD or YYYY-MM)."""
    if not date_str:
        return None
    try:
        if len(date_str) == 7:  # YYYY-MM
            return datetime.strptime(date_str, "%Y-%m").date()
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _slugify(name: str) -> str:
    """Create a URL-safe slug from a drug name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")[:200]


def _extract_interventions(study: dict) -> list[dict]:
    """Extract drug/biologic interventions from a study."""
    interventions = []
    protocol = study.get("protocolSection", {})
    arms_module = protocol.get("armsInterventionsModule", {})

    for intervention in arms_module.get("interventions", []):
        int_type = intervention.get("type", "")
        if int_type in ("DRUG", "BIOLOGICAL", "GENETIC", "COMBINATION_PRODUCT"):
            interventions.append({
                "name": intervention.get("name", "Unknown"),
                "type": int_type,
                "description": intervention.get("description", ""),
            })

    return interventions


def _fetch_studies(sponsor_name: str, page_token: str | None = None) -> dict:
    """Blocking HTTP call to ClinicalTrials.gov (run in thread pool)."""
    params = {
        "query.spons": sponsor_name,
        "pageSize": 100,
    }
    if page_token:
        params["pageToken"] = page_token
    resp = _session.get(f"{CT_GOV_BASE_URL}/studies", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


async def sync_trials_for_company(
    db: AsyncSession,
    ticker: str,
    sponsor_names: list[str],
) -> int:
    """
    Sync trials for a single company from ClinicalTrials.gov.
    Returns the number of trials synced.
    """
    count = 0

    for sponsor_name in sponsor_names:
        try:
            # Query ClinicalTrials.gov API v2 (using requests in thread pool)
            loop = asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(_executor, _fetch_studies, sponsor_name, None)
            except Exception as e:
                if "429" in str(e):
                    logger.warning(f"Rate limited on ClinicalTrials.gov, waiting 60s")
                    await asyncio.sleep(60)
                    data = await loop.run_in_executor(_executor, _fetch_studies, sponsor_name, None)
                else:
                    logger.warning(f"ClinicalTrials.gov error for {sponsor_name}: {e}")
                    continue

            studies = data.get("studies", [])

            for study in studies:
                try:
                    protocol = study.get("protocolSection", {})
                    id_module = protocol.get("identificationModule", {})
                    status_module = protocol.get("statusModule", {})
                    design_module = protocol.get("designModule", {})
                    desc_module = protocol.get("descriptionModule", {})
                    enrollment_module = protocol.get("designModule", {}).get("enrollmentInfo", {})
                    conditions_module = protocol.get("conditionsModule", {})
                    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

                    nct_id = id_module.get("nctId")
                    if not nct_id:
                        continue

                    # Get phase
                    phases = design_module.get("phases", [])
                    raw_phase = phases[0] if phases else None
                    if raw_phase and len(phases) > 1:
                        # Handle "PHASE1|PHASE2" type entries
                        raw_phase = phases[-1]  # Use the higher phase
                    phase = PHASE_MAP.get(raw_phase, raw_phase)

                    # Get conditions (first one = primary indication)
                    conditions = conditions_module.get("conditions", [])
                    indication = conditions[0] if conditions else None
                    therapeutic_area = _classify_therapeutic_area(indication) if indication else None

                    # Get dates
                    start_date = _parse_date(
                        status_module.get("startDateStruct", {}).get("date")
                    )
                    primary_completion = _parse_date(
                        status_module.get("primaryCompletionDateStruct", {}).get("date")
                    )
                    completion = _parse_date(
                        status_module.get("completionDateStruct", {}).get("date")
                    )
                    results_posted = _parse_date(
                        status_module.get("resultsFirstPostDateStruct", {}).get("date")
                    )
                    last_update = _parse_date(
                        status_module.get("lastUpdatePostDateStruct", {}).get("date")
                    )

                    # Get sponsor name
                    lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", sponsor_name)

                    # Get enrollment
                    enrollment = None
                    enroll_info = design_module.get("enrollmentInfo", {})
                    if enroll_info:
                        enrollment = enroll_info.get("count")

                    # Extract interventions and create/link drugs
                    interventions = _extract_interventions(study)
                    drug_id = None
                    if interventions:
                        drug_info = interventions[0]  # Primary intervention
                        drug_name = drug_info["name"]
                        drug_slug = f"{ticker.lower()}-{_slugify(drug_name)}"

                        # Upsert drug
                        drug_result = await db.execute(
                            select(Drug).where(Drug.drug_id == drug_slug)
                        )
                        drug = drug_result.scalar_one_or_none()

                        if not drug:
                            drug = Drug(
                                drug_id=drug_slug,
                                drug_name=drug_name,
                                company_ticker=ticker,
                                mechanism=drug_info.get("description", "")[:500] if drug_info.get("description") else None,
                                therapeutic_area=therapeutic_area,
                                indication=indication,
                                highest_phase=phase,
                                status="ACTIVE",
                            )
                            db.add(drug)
                            await db.flush()
                        else:
                            # Update highest phase if this trial is higher
                            if phase and PHASE_RANK.get(phase, 0) > PHASE_RANK.get(drug.highest_phase, 0):
                                drug.highest_phase = phase
                            if therapeutic_area and not drug.therapeutic_area:
                                drug.therapeutic_area = therapeutic_area

                        drug_id = drug_slug

                    # Upsert trial
                    async with db.begin_nested():
                        stmt = pg_upsert(Trial).values(
                            nct_id=nct_id,
                            drug_id=drug_id,
                            company_ticker=ticker,
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
                                "drug_id": stmt.excluded.drug_id,
                                "company_ticker": stmt.excluded.company_ticker,
                                "phase": stmt.excluded.phase,
                                "overall_status": stmt.excluded.overall_status,
                                "enrollment": stmt.excluded.enrollment,
                                "primary_completion_date": stmt.excluded.primary_completion_date,
                                "completion_date": stmt.excluded.completion_date,
                                "updated_at": stmt.excluded.updated_at,
                            },
                        )
                        await db.execute(stmt)
                    count += 1

                except Exception as e:
                    logger.warning(f"Error processing study {study.get('protocolSection', {}).get('identificationModule', {}).get('nctId', '?')}: {e}")
                    continue

            # Handle pagination
            next_token = data.get("nextPageToken")
            while next_token:
                await asyncio.sleep(1.5)  # Rate limit
                try:
                    data = await loop.run_in_executor(_executor, _fetch_studies, sponsor_name, next_token)
                except Exception:
                    break
                studies = data.get("studies", [])

                for study in studies:
                    try:
                        protocol = study.get("protocolSection", {})
                        id_module = protocol.get("identificationModule", {})
                        nct_id = id_module.get("nctId")
                        if not nct_id:
                            continue

                        status_module = protocol.get("statusModule", {})
                        design_module = protocol.get("designModule", {})
                        desc_module = protocol.get("descriptionModule", {})
                        conditions_module = protocol.get("conditionsModule", {})
                        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

                        phases = design_module.get("phases", [])
                        raw_phase = phases[-1] if phases else None
                        phase = PHASE_MAP.get(raw_phase, raw_phase)

                        conditions = conditions_module.get("conditions", [])
                        indication = conditions[0] if conditions else None
                        therapeutic_area = _classify_therapeutic_area(indication) if indication else None

                        lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", sponsor_name)

                        async with db.begin_nested():
                            stmt = pg_upsert(Trial).values(
                                nct_id=nct_id,
                                company_ticker=ticker,
                                sponsor_name=lead_sponsor,
                                title=id_module.get("officialTitle") or id_module.get("briefTitle", "Unknown"),
                                brief_summary=(desc_module.get("briefSummary", "") or "")[:5000],
                                phase=phase,
                                overall_status=status_module.get("overallStatus"),
                                therapeutic_area=therapeutic_area,
                                indication=indication,
                                enrollment=design_module.get("enrollmentInfo", {}).get("count"),
                                start_date=_parse_date(status_module.get("startDateStruct", {}).get("date")),
                                primary_completion_date=_parse_date(status_module.get("primaryCompletionDateStruct", {}).get("date")),
                                completion_date=_parse_date(status_module.get("completionDateStruct", {}).get("date")),
                                study_type=design_module.get("studyType"),
                                updated_at=datetime.utcnow(),
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["nct_id"],
                                set_={"updated_at": stmt.excluded.updated_at},
                            )
                            await db.execute(stmt)
                        count += 1
                    except Exception:
                        continue

                next_token = data.get("nextPageToken")

        except Exception as e:
            logger.warning(f"Error syncing trials for {ticker} ({sponsor_name}): {e}")
            continue

    return count


def _classify_therapeutic_area(condition: str | None) -> str | None:
    """Classify a condition into a broad therapeutic area."""
    if not condition:
        return None

    condition_lower = condition.lower()

    oncology_terms = ["cancer", "tumor", "tumour", "carcinoma", "lymphoma", "leukemia",
                      "melanoma", "sarcoma", "myeloma", "neoplasm", "oncol", "glioblastoma",
                      "neuroblastoma", "mesothelioma"]
    if any(t in condition_lower for t in oncology_terms):
        return "Oncology"

    immunology_terms = ["autoimmune", "rheumatoid", "lupus", "psoriasis", "crohn",
                        "colitis", "multiple sclerosis", "arthritis", "inflammation",
                        "immune", "atopic dermatitis", "eczema"]
    if any(t in condition_lower for t in immunology_terms):
        return "Immunology"

    cns_terms = ["alzheimer", "parkinson", "epilepsy", "seizure", "schizophrenia",
                 "depression", "anxiety", "bipolar", "dementia", "neuropath",
                 "amyotrophic", "huntington", "migraine", "pain", "cns"]
    if any(t in condition_lower for t in cns_terms):
        return "CNS/Neurology"

    cardio_terms = ["heart", "cardiac", "cardiovascular", "hypertension", "atherosclerosis",
                    "thrombosis", "stroke", "arrhythmia", "heart failure"]
    if any(t in condition_lower for t in cardio_terms):
        return "Cardiovascular"

    metabolic_terms = ["diabetes", "obesity", "metabolic", "cholesterol", "lipid",
                       "nash", "fatty liver", "glycogen"]
    if any(t in condition_lower for t in metabolic_terms):
        return "Metabolic"

    infectious_terms = ["hiv", "hepatitis", "covid", "influenza", "rsv", "infection",
                        "viral", "bacterial", "fungal", "tuberculosis", "malaria", "vaccine"]
    if any(t in condition_lower for t in infectious_terms):
        return "Infectious Disease"

    rare_terms = ["rare", "orphan", "duchenne", "cystic fibrosis", "hemophilia",
                  "sickle cell", "thalassemia", "gaucher", "fabry", "pompe",
                  "spinal muscular", "muscular dystrophy"]
    if any(t in condition_lower for t in rare_terms):
        return "Rare Disease"

    gene_terms = ["gene therapy", "cell therapy", "car-t", "car t", "crispr",
                  "genome", "genetic"]
    if any(t in condition_lower for t in gene_terms):
        return "Gene/Cell Therapy"

    respiratory_terms = ["asthma", "copd", "pulmonary", "respiratory", "lung disease", "fibrosis"]
    if any(t in condition_lower for t in respiratory_terms):
        return "Respiratory"

    eye_terms = ["macular", "retinal", "glaucoma", "ophthalm", "eye", "vision", "blindness"]
    if any(t in condition_lower for t in eye_terms):
        return "Ophthalmology"

    return "Other"


async def sync_all_trials(db: AsyncSession) -> int:
    """
    Sync trials for all biotech companies.
    Returns total number of trials synced.
    """
    log = SyncLog(
        sync_type="TRIALS",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        # Get all biotech companies with their sponsor aliases
        result = await db.execute(
            select(Company).where(Company.sic_code.in_(BIOTECH_SIC_CODES))
        )
        companies = result.scalars().all()

        total_count = 0

        for i, company in enumerate(companies):
            # Get sponsor aliases for this company
            alias_result = await db.execute(
                select(SponsorAlias.alias_name).where(
                    SponsorAlias.ticker == company.ticker
                )
            )
            aliases = [r[0] for r in alias_result.all()]

            # Also try the company name itself
            if company.name and company.name not in aliases:
                aliases.append(company.name)

            if not aliases:
                continue

            count = await sync_trials_for_company(db, company.ticker, aliases)
            total_count += count

            # Commit after each company
            await db.commit()

            logger.info(f"[{i+1}/{len(companies)}] {company.ticker}: {count} trials synced")

            # Rate limit: ClinicalTrials.gov allows ~50 req/min
            await asyncio.sleep(1.5)

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = total_count
        await db.commit()

        logger.info(f"Trial sync complete: {total_count} trials synced for {len(companies)} companies")
        return total_count

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"Trial sync failed: {e}")
        raise
