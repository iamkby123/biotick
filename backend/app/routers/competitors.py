"""
Competitor analysis endpoints.

Cross-references drug pipelines to find competing drugs targeting
the same indication, and analyzes competitive landscape.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.database import get_db
from app.models.drug import Drug
from app.models.company import Company
from app.models.trial import Trial
from app.cache.memory_cache import cache

router = APIRouter(prefix="/api/competitors", tags=["competitors"])


@router.get("/indications")
async def get_indications_matrix(
    limit: int = Query(30, ge=5, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a matrix of the top indications by total drug count, grouped by phase.
    Each row is an indication, each phase column is a drug count. Also includes
    the number of distinct companies targeting each indication.
    """
    cache_key = f"indication_matrix:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Top indications by drug count (excluding nulls / placebos)
    top_q = await db.execute(
        select(
            Drug.indication,
            func.count(Drug.drug_id).label("cnt"),
            func.count(func.distinct(Drug.company_ticker)).label("companies"),
        )
        .where(
            Drug.indication.isnot(None),
            Drug.status != "PLACEBO",
        )
        .group_by(Drug.indication)
        .order_by(func.count(Drug.drug_id).desc())
        .limit(limit)
    )
    top_rows = top_q.all()
    top_indications = [r[0] for r in top_rows]

    if not top_indications:
        empty: dict = {"indications": [], "phases": ["PHASE1", "PHASE2", "PHASE3", "PHASE4", "APPROVED"]}
        cache.set(cache_key, empty, 600)
        return empty

    # Fetch phase breakdown for these indications
    phase_q = await db.execute(
        select(
            Drug.indication,
            Drug.highest_phase,
            func.count(Drug.drug_id).label("cnt"),
        )
        .where(
            Drug.indication.in_(top_indications),
            Drug.status != "PLACEBO",
        )
        .group_by(Drug.indication, Drug.highest_phase)
    )
    phase_rows = phase_q.all()

    # Build matrix: indication -> { phase -> count, total, companies }
    matrix: dict = {}
    company_lookup = {r[0]: r[2] for r in top_rows}
    total_lookup = {r[0]: r[1] for r in top_rows}
    for ind in top_indications:
        matrix[ind] = {
            "indication": ind,
            "total": total_lookup.get(ind, 0),
            "companies": company_lookup.get(ind, 0),
            "phases": {},
        }

    for indication, phase, cnt in phase_rows:
        if indication in matrix:
            matrix[indication]["phases"][phase or "UNKNOWN"] = cnt

    phases = ["PHASE1", "PHASE2", "PHASE3", "PHASE4", "APPROVED"]
    response = {
        "indications": list(matrix.values()),
        "phases": phases,
    }
    cache.set(cache_key, response, 600)
    return response


@router.get("/drug/{drug_id}")
async def get_drug_competitors(
    drug_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Find competing drugs targeting the same indication."""
    # Get the drug
    result = await db.execute(select(Drug).where(Drug.drug_id == drug_id))
    drug = result.scalar_one_or_none()
    if not drug or not drug.indication:
        return {"competitors": [], "message": "No indication data to find competitors"}

    # Search for drugs with similar indications
    # Use keyword matching on indication
    keywords = [w.strip().lower() for w in drug.indication.split() if len(w.strip()) > 3]
    # Take the most specific keywords
    skip_words = {"with", "type", "from", "that", "this", "have", "been", "were", "other", "patients", "subjects", "study"}
    keywords = [k for k in keywords if k not in skip_words][:3]

    if not keywords:
        return {"competitors": [], "message": "Could not extract indication keywords"}

    # Build query for competing drugs
    conditions = [Drug.indication.ilike(f"%{kw}%") for kw in keywords]
    result = await db.execute(
        select(Drug, Company.name, Company.price, Company.market_cap)
        .join(Company, Drug.company_ticker == Company.ticker)
        .where(
            and_(
                Drug.drug_id != drug_id,
                Drug.status != "PLACEBO",
                or_(*conditions),
            )
        )
        .order_by(Drug.highest_phase.desc())
        .limit(20)
    )
    rows = result.all()

    competitors = []
    for comp_drug, company_name, price, market_cap in rows:
        competitors.append({
            "drug_id": comp_drug.drug_id,
            "drug_name": comp_drug.drug_name,
            "company_ticker": comp_drug.company_ticker,
            "company_name": company_name,
            "company_price": price,
            "company_market_cap": market_cap,
            "indication": comp_drug.indication,
            "phase": comp_drug.highest_phase,
            "therapeutic_area": comp_drug.therapeutic_area,
            "mechanism": comp_drug.mechanism,
            "status": comp_drug.status,
        })

    return {
        "drug": {
            "drug_id": drug.drug_id,
            "drug_name": drug.drug_name,
            "indication": drug.indication,
            "phase": drug.highest_phase,
            "company_ticker": drug.company_ticker,
        },
        "competitors": competitors,
        "keywords_used": keywords,
    }


@router.get("/company/{ticker}")
async def get_company_competitors(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Find companies competing in the same therapeutic areas."""
    ticker = ticker.upper()

    # Get this company's therapeutic areas
    result = await db.execute(
        select(Drug.therapeutic_area, func.count().label("cnt"))
        .where(Drug.company_ticker == ticker, Drug.therapeutic_area.isnot(None))
        .group_by(Drug.therapeutic_area)
        .order_by(func.count().desc())
    )
    areas = result.all()

    if not areas:
        return {"competitors": [], "areas": []}

    top_areas = [a[0] for a in areas[:3]]

    # Find other companies in the same areas
    result = await db.execute(
        select(
            Company.ticker,
            Company.name,
            Company.price,
            Company.market_cap,
            func.count(Drug.drug_id).label("pipeline_size"),
            func.max(Drug.highest_phase).label("max_phase"),
        )
        .join(Drug, Company.ticker == Drug.company_ticker)
        .where(
            Company.ticker != ticker,
            Drug.therapeutic_area.in_(top_areas),
            Drug.status != "PLACEBO",
        )
        .group_by(Company.ticker, Company.name, Company.price, Company.market_cap)
        .order_by(func.count(Drug.drug_id).desc())
        .limit(15)
    )
    rows = result.all()

    competitors = []
    for comp_ticker, name, price, mcap, pipeline, max_phase in rows:
        # Get their therapeutic areas overlap
        area_result = await db.execute(
            select(Drug.therapeutic_area, func.count())
            .where(Drug.company_ticker == comp_ticker, Drug.therapeutic_area.in_(top_areas))
            .group_by(Drug.therapeutic_area)
        )
        overlap = {r[0]: r[1] for r in area_result.all()}

        competitors.append({
            "ticker": comp_ticker,
            "name": name,
            "price": price,
            "market_cap": mcap,
            "pipeline_size": pipeline,
            "max_phase": max_phase,
            "overlapping_areas": overlap,
        })

    return {
        "company": ticker,
        "therapeutic_areas": top_areas,
        "competitors": competitors,
    }


@router.get("/indication/{indication}")
async def get_indication_landscape(
    indication: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the competitive landscape for an indication — all drugs targeting it."""
    result = await db.execute(
        select(Drug, Company.name, Company.price, Company.market_cap)
        .join(Company, Drug.company_ticker == Company.ticker)
        .where(
            Drug.indication.ilike(f"%{indication}%"),
            Drug.status != "PLACEBO",
        )
        .order_by(Drug.highest_phase.desc())
        .limit(30)
    )
    rows = result.all()

    # Group by phase
    by_phase: dict = {}
    for drug, company_name, price, mcap in rows:
        phase = drug.highest_phase or "Unknown"
        if phase not in by_phase:
            by_phase[phase] = []
        by_phase[phase].append({
            "drug_name": drug.drug_name,
            "company_ticker": drug.company_ticker,
            "company_name": company_name,
            "company_price": price,
            "market_cap": mcap,
            "mechanism": drug.mechanism,
            "drug_id": drug.drug_id,
        })

    return {
        "indication": indication,
        "total_drugs": len(rows),
        "by_phase": by_phase,
    }
