from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from math import ceil

from app.database import get_db
from app.models.drug import Drug
from app.models.trial import Trial
from app.schemas.drug import DrugResponse, TrialResponse, DrugWithTrials

router = APIRouter(prefix="/api", tags=["drugs", "trials"])


@router.get("/companies/{ticker}/pipeline", response_model=list[DrugResponse])
async def get_company_pipeline(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all drugs for a company (pipeline view)."""
    result = await db.execute(
        select(Drug)
        .where(Drug.company_ticker == ticker.upper())
        .order_by(Drug.highest_phase.desc())
    )
    drugs = result.scalars().all()
    return [DrugResponse.model_validate(d) for d in drugs]


@router.get("/drugs/{drug_id}", response_model=DrugWithTrials)
async def get_drug_detail(
    drug_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get drug detail with all its trials."""
    result = await db.execute(
        select(Drug)
        .options(selectinload(Drug.trials))
        .where(Drug.drug_id == drug_id)
    )
    drug = result.scalar_one_or_none()

    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")

    drug_data = DrugWithTrials.model_validate(drug)
    drug_data.trials = [TrialResponse.model_validate(t) for t in drug.trials]

    # Also search for related trials from the full database by drug name and indication
    if drug.drug_name and len(drug_data.trials) < 20:
        related_result = await db.execute(
            select(Trial)
            .where(
                Trial.drug_id.is_(None),  # Not already linked
                Trial.title.ilike(f"%{drug.drug_name}%"),
            )
            .order_by(Trial.start_date.desc().nullslast())
            .limit(20)
        )
        related = related_result.scalars().all()
        existing_ncts = {t.nct_id for t in drug_data.trials}
        for t in related:
            if t.nct_id not in existing_ncts:
                drug_data.trials.append(TrialResponse.model_validate(t))

    return drug_data


@router.get("/companies/{ticker}/all-trials")
async def get_company_all_trials(
    ticker: str,
    phase: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get all trials for a company including from bulk import, with filtering."""
    query = select(Trial).where(Trial.company_ticker == ticker.upper())

    if phase:
        query = query.where(Trial.phase == phase)
    if status:
        query = query.where(Trial.overall_status == status)
    if search:
        query = query.where(Trial.title.ilike(f"%{search}%"))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort by date, paginate
    query = query.order_by(Trial.start_date.desc().nullslast()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    trials = result.scalars().all()

    return {
        "trials": [TrialResponse.model_validate(t) for t in trials],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/trials", response_model=dict)
async def list_trials(
    company_ticker: str | None = Query(None),
    drug_id: str | None = Query(None),
    phase: str | None = Query(None),
    status: str | None = Query(None),
    therapeutic_area: str | None = Query(None),
    search: str | None = Query(None),
    sort_by: str = Query("primary_completion_date"),
    sort_dir: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List and filter trials."""
    query = select(Trial)

    if company_ticker:
        query = query.where(Trial.company_ticker == company_ticker.upper())
    if drug_id:
        query = query.where(Trial.drug_id == drug_id)
    if phase:
        query = query.where(Trial.phase == phase)
    if status:
        query = query.where(Trial.overall_status == status)
    if therapeutic_area:
        query = query.where(Trial.therapeutic_area.ilike(f"%{therapeutic_area}%"))
    if search:
        query = query.where(Trial.title.ilike(f"%{search}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort
    sort_col = getattr(Trial, sort_by, Trial.primary_completion_date)
    if sort_dir == "desc":
        query = query.order_by(sort_col.desc().nullslast())
    else:
        query = query.order_by(sort_col.asc().nullslast())

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    trials = result.scalars().all()

    return {
        "trials": [TrialResponse.model_validate(t) for t in trials],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/trials/{nct_id}", response_model=TrialResponse)
async def get_trial(
    nct_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single trial by NCT ID."""
    result = await db.execute(
        select(Trial).where(Trial.nct_id == nct_id)
    )
    trial = result.scalar_one_or_none()
    if not trial:
        raise HTTPException(status_code=404, detail=f"Trial {nct_id} not found")
    return TrialResponse.model_validate(trial)
