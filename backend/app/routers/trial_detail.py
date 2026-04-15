"""
Detailed trial information endpoint.
Fetches full trial data from ClinicalTrials.gov API for rich detail pages.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import requests as req_lib
from fastapi import APIRouter, HTTPException

from app.cache.memory_cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trials", tags=["trial-detail"])
_executor = ThreadPoolExecutor(max_workers=2)

_session = req_lib.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})


def _fetch_trial_detail(nct_id: str) -> dict:
    """Fetch full trial detail from ClinicalTrials.gov (blocking)."""
    resp = _session.get(
        f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
        timeout=15,
    )
    if resp.status_code != 200:
        return {}
    return resp.json()


@router.get("/{nct_id}/detail")
async def get_trial_full_detail(nct_id: str):
    """Get comprehensive trial details from ClinicalTrials.gov."""
    cache_key = f"trial_detail:{nct_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        raw = await loop.run_in_executor(_executor, _fetch_trial_detail, nct_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trial: {e}")

    if not raw:
        raise HTTPException(status_code=404, detail=f"Trial {nct_id} not found on ClinicalTrials.gov")

    # Parse the raw response into a clean structure
    proto = raw.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    desc = proto.get("descriptionModule", {})
    design = proto.get("designModule", {})
    arms = proto.get("armsInterventionsModule", {})
    outcomes = proto.get("outcomesModule", {})
    eligibility = proto.get("eligibilityModule", {})
    contacts = proto.get("contactsLocationsModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {})
    conditions = proto.get("conditionsModule", {})
    references = proto.get("referencesModule", {})
    oversight = proto.get("oversightModule", {})

    # Build structured response
    result = {
        "nct_id": ident.get("nctId"),
        "title": ident.get("officialTitle") or ident.get("briefTitle"),
        "brief_title": ident.get("briefTitle"),
        "acronym": ident.get("acronym"),
        "status": status.get("overallStatus"),
        "status_verified_date": status.get("statusVerifiedDate"),
        "start_date": status.get("startDateStruct", {}).get("date"),
        "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
        "completion_date": status.get("completionDateStruct", {}).get("date"),
        "brief_summary": desc.get("briefSummary"),
        "detailed_description": desc.get("detailedDescription"),

        # Study design
        "study_type": design.get("studyType"),
        "phases": design.get("phases", []),
        "allocation": design.get("designInfo", {}).get("allocation"),
        "intervention_model": design.get("designInfo", {}).get("interventionModel"),
        "primary_purpose": design.get("designInfo", {}).get("primaryPurpose"),
        "masking": design.get("designInfo", {}).get("maskingInfo", {}).get("masking"),
        "masking_details": design.get("designInfo", {}).get("maskingInfo", {}).get("maskingDescription"),
        "who_masked": design.get("designInfo", {}).get("maskingInfo", {}).get("whoMasked", []),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "enrollment_type": design.get("enrollmentInfo", {}).get("type"),

        # Arms and interventions
        "arms": [
            {
                "label": arm.get("label"),
                "type": arm.get("type"),
                "description": arm.get("description"),
            }
            for arm in arms.get("armGroups", [])
        ],
        "interventions": [
            {
                "name": intv.get("name"),
                "type": intv.get("type"),
                "description": intv.get("description"),
                "arm_labels": intv.get("armGroupLabels", []),
            }
            for intv in arms.get("interventions", [])
        ],

        # Outcomes
        "primary_outcomes": [
            {
                "measure": o.get("measure"),
                "description": o.get("description"),
                "timeframe": o.get("timeFrame"),
            }
            for o in outcomes.get("primaryOutcomes", [])
        ],
        "secondary_outcomes": [
            {
                "measure": o.get("measure"),
                "description": o.get("description"),
                "timeframe": o.get("timeFrame"),
            }
            for o in outcomes.get("secondaryOutcomes", [])
        ],

        # Eligibility
        "eligibility": {
            "criteria": eligibility.get("eligibilityCriteria"),
            "sex": eligibility.get("sex"),
            "minimum_age": eligibility.get("minimumAge"),
            "maximum_age": eligibility.get("maximumAge"),
            "healthy_volunteers": eligibility.get("healthyVolunteers"),
        },

        # Sponsor
        "sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "sponsor_type": sponsor.get("leadSponsor", {}).get("class"),
        "collaborators": [
            c.get("name") for c in sponsor.get("collaborators", [])
        ],

        # Conditions
        "conditions": conditions.get("conditions", []),
        "keywords": conditions.get("keywords", []),

        # Oversight
        "has_dmc": oversight.get("oversightHasDmc"),
        "is_fda_regulated_drug": oversight.get("isFDARegulatedDrug"),
        "is_fda_regulated_device": oversight.get("isFDARegulatedDevice"),

        # Locations count
        "locations_count": len(contacts.get("locations", [])),

        # References
        "references": [
            {
                "pmid": ref.get("pmid"),
                "citation": ref.get("citation"),
                "type": ref.get("type"),
            }
            for ref in references.get("references", [])
        ],

        # URL
        "url": f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
    }

    cache.set(cache_key, result, 1800)  # Cache 30 min
    return result
