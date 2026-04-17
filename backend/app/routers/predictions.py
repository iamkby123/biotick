"""Trial predictions: Shot on Goal score, sponsor track record, red flags."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from math import ceil

from app.database import get_db

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/trial/{nct_id}")
async def get_trial_prediction(nct_id: str, db: AsyncSession = Depends(get_db)):
    """Get Shot on Goal score and red flags for a trial."""
    result = await db.execute(
        text("""SELECT tp.shot_on_goal, tp.phase_success_rate, tp.indication_difficulty,
                       tp.sponsor_credibility, tp.red_flags, tp.risk_level, tp.updated_at
                FROM trial_predictions tp WHERE tp.nct_id = :nct"""),
        {"nct": nct_id.upper()},
    )
    row = result.fetchone()
    if not row:
        return {"nct_id": nct_id, "scored": False}
    return {
        "nct_id": nct_id,
        "scored": True,
        "shot_on_goal": row[0],
        "phase_success_rate": row[1],
        "indication_difficulty": row[2],
        "sponsor_credibility": row[3],
        "red_flags": row[4] if row[4] else [],
        "risk_level": row[5],
        "updated_at": row[6].isoformat() if row[6] else None,
    }


@router.get("/sponsor/{ticker}")
async def get_sponsor_track_record(ticker: str, db: AsyncSession = Depends(get_db)):
    """Get sponsor's historical trial success rates."""
    result = await db.execute(
        text("""SELECT total_trials, completed_trials, terminated_trials,
                       phase1_success_rate, phase2_success_rate, phase3_success_rate,
                       approval_count, overall_success_rate
                FROM sponsor_track_records WHERE company_ticker = :t"""),
        {"t": ticker.upper()},
    )
    row = result.fetchone()
    if not row:
        return {"ticker": ticker, "has_data": False, "message": "Insufficient historical data (need 3+ trials)"}
    return {
        "ticker": ticker.upper(),
        "has_data": True,
        "total_trials": row[0],
        "completed_trials": row[1],
        "terminated_trials": row[2],
        "phase1_success_rate": row[3],
        "phase2_success_rate": row[4],
        "phase3_success_rate": row[5],
        "approval_count": row[6],
        "overall_success_rate": row[7],
    }


@router.get("/high-conviction")
async def get_high_conviction_trials(
    limit: int = Query(50, ge=1, le=200),
    min_phase: str = Query("PHASE2", description="Min phase: PHASE1, PHASE2, PHASE3"),
    db: AsyncSession = Depends(get_db),
):
    """Get trials with highest Shot on Goal scores and no red flags."""
    phase_filter = ""
    if min_phase == "PHASE2":
        phase_filter = "AND t.phase IN ('PHASE2','PHASE3','PHASE4')"
    elif min_phase == "PHASE3":
        phase_filter = "AND t.phase IN ('PHASE3','PHASE4')"

    result = await db.execute(
        text(f"""SELECT t.nct_id, t.company_ticker, t.phase, t.indication, t.overall_status,
                        t.primary_completion_date, t.enrollment, t.title,
                        tp.shot_on_goal, tp.risk_level, tp.red_flags,
                        c.name as company_name, c.market_cap, c.price
                 FROM trial_predictions tp
                 JOIN trials t ON t.nct_id = tp.nct_id
                 LEFT JOIN companies c ON c.ticker = t.company_ticker
                 WHERE tp.risk_level = 'LOW'
                 {phase_filter}
                 ORDER BY tp.shot_on_goal DESC
                 LIMIT :lim"""),
        {"lim": limit},
    )
    trials = []
    for row in result.fetchall():
        trials.append({
            "nct_id": row[0],
            "ticker": row[1],
            "phase": row[2],
            "indication": row[3],
            "overall_status": row[4],
            "primary_completion_date": row[5].isoformat() if row[5] else None,
            "enrollment": row[6],
            "title": row[7],
            "shot_on_goal": row[8],
            "risk_level": row[9],
            "red_flags": row[10] if row[10] else [],
            "company_name": row[11],
            "market_cap": row[12],
            "price": row[13],
        })
    return {"trials": trials, "total": len(trials)}


@router.get("/red-flags")
async def get_red_flag_trials(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get trials with red flags (high risk)."""
    result = await db.execute(
        text("""SELECT t.nct_id, t.company_ticker, t.phase, t.indication,
                       tp.shot_on_goal, tp.risk_level, tp.red_flags,
                       c.name, c.price, c.market_cap
                FROM trial_predictions tp
                JOIN trials t ON t.nct_id = tp.nct_id
                LEFT JOIN companies c ON c.ticker = t.company_ticker
                WHERE tp.risk_level = 'HIGH'
                ORDER BY jsonb_array_length(COALESCE(tp.red_flags, '[]'::jsonb)) DESC, tp.shot_on_goal ASC
                LIMIT :lim"""),
        {"lim": limit},
    )
    trials = []
    for row in result.fetchall():
        trials.append({
            "nct_id": row[0],
            "ticker": row[1],
            "phase": row[2],
            "indication": row[3],
            "shot_on_goal": row[4],
            "risk_level": row[5],
            "red_flags": row[6] if row[6] else [],
            "company_name": row[7],
            "price": row[8],
            "market_cap": row[9],
        })
    return {"trials": trials, "total": len(trials)}


@router.get("/company/{ticker}/trials")
async def get_company_trial_predictions(ticker: str, db: AsyncSession = Depends(get_db)):
    """Get all scored trials for a company."""
    result = await db.execute(
        text("""SELECT t.nct_id, t.phase, t.indication, t.title, t.overall_status,
                       t.primary_completion_date, tp.shot_on_goal, tp.risk_level, tp.red_flags
                FROM trial_predictions tp
                JOIN trials t ON t.nct_id = tp.nct_id
                WHERE t.company_ticker = :t
                ORDER BY tp.shot_on_goal DESC"""),
        {"t": ticker.upper()},
    )
    trials = []
    for row in result.fetchall():
        trials.append({
            "nct_id": row[0],
            "phase": row[1],
            "indication": row[2],
            "title": row[3],
            "overall_status": row[4],
            "primary_completion_date": row[5].isoformat() if row[5] else None,
            "shot_on_goal": row[6],
            "risk_level": row[7],
            "red_flags": row[8] if row[8] else [],
        })
    return {"ticker": ticker.upper(), "trials": trials, "total": len(trials)}
