"""Per-trial factor analysis.

Deterministic rule-based signals (good/bad) for each trial. Replaces the
earlier XGBoost "Shot on Goal" percentile, which was accurate but opaque -
factors are legible so users can actually reason about a trial.

Factors are computed on demand from:
- trials table (phase, enrollment, status, why_stopped, has_results)
- sponsor_track_records (sponsor's historical trial success)
- indication_success_rates (how often this indication advances)
- companies (market cap as a proxy for resources / financing risk)

No ML model is loaded.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


# ─── Factor computation ──────────────────────────────────────────────────


def _compute_factors(trial, sponsor, indication_rate, market_cap):
    """Return a list of {label, type, detail} from a trial + its context.

    `type` is "positive" or "negative". Order is roughly by importance
    within each type. The frontend groups by type.
    """
    factors = []

    phase = trial.get("phase")
    enrollment = trial.get("enrollment")
    status = trial.get("overall_status")
    why_stopped = trial.get("why_stopped")
    has_results = trial.get("has_results")

    # ── Status signals (strongest) ─────────────────────────────────
    if status in ("TERMINATED", "WITHDRAWN"):
        factors.append({
            "type": "negative",
            "label": "Trial terminated",
            "detail": why_stopped or "No reason provided. Terminated trials often indicate safety issues, futility, or enrollment failure.",
        })
    elif status == "SUSPENDED":
        factors.append({
            "type": "negative",
            "label": "Trial suspended",
            "detail": why_stopped or "Enrollment or activities temporarily halted. May resume or be discontinued.",
        })
    elif status == "COMPLETED":
        factors.append({
            "type": "positive",
            "label": "Trial completed",
            "detail": "Enrollment and follow-up finished successfully.",
        })
        if has_results:
            factors.append({
                "type": "positive",
                "label": "Results published",
                "detail": "Results posted on ClinicalTrials.gov - data is publicly available.",
            })

    # ── Enrollment signals (phase-adjusted) ────────────────────────
    if enrollment is not None:
        if phase == "PHASE3":
            if enrollment >= 500:
                factors.append({
                    "type": "positive",
                    "label": f"Well-powered Phase 3 ({enrollment:,})",
                    "detail": "Large enrollment gives good statistical power to detect treatment effects.",
                })
            elif enrollment < 150:
                factors.append({
                    "type": "negative",
                    "label": f"Small Phase 3 ({enrollment})",
                    "detail": "Phase 3 trials typically enroll 300-3000 participants. Small Phase 3s risk being underpowered.",
                })
        elif phase == "PHASE2":
            if enrollment >= 150:
                factors.append({
                    "type": "positive",
                    "label": f"Solid Phase 2 enrollment ({enrollment})",
                    "detail": "Enrollment is large enough to produce interpretable efficacy signals.",
                })
            elif enrollment < 30:
                factors.append({
                    "type": "negative",
                    "label": f"Small Phase 2 ({enrollment})",
                    "detail": "Very small Phase 2 may not detect real signals or distinguish noise from effect.",
                })
        elif phase == "PHASE1" and enrollment < 10:
            factors.append({
                "type": "negative",
                "label": f"Very small Phase 1 ({enrollment})",
                "detail": "Below typical first-in-human cohort sizes.",
            })

    # ── Sponsor track record ───────────────────────────────────────
    if sponsor:
        approvals = sponsor.get("approval_count", 0) or 0
        total = sponsor.get("total_trials", 0) or 0
        overall = sponsor.get("overall_success_rate") or 0.0

        if approvals >= 3:
            factors.append({
                "type": "positive",
                "label": f"Sponsor has {approvals}+ FDA approvals",
                "detail": "Sponsor has successfully taken drugs through approval before. Execution capability is proven.",
            })
        elif approvals >= 1:
            factors.append({
                "type": "positive",
                "label": f"Sponsor has prior FDA approval",
                "detail": f"{approvals} approval on record. Sponsor has gone the full distance before.",
            })

        if total >= 10 and overall > 0.55:
            factors.append({
                "type": "positive",
                "label": "Strong sponsor completion rate",
                "detail": f"Sponsor has completed {int(overall*100)}% of {total} historical trials - high execution consistency.",
            })
        elif total >= 5 and overall < 0.25:
            factors.append({
                "type": "negative",
                "label": "Weak sponsor completion rate",
                "detail": f"Only {int(overall*100)}% of this sponsor's {total} historical trials have completed. High termination history is concerning.",
            })

        if total < 3 and approvals == 0:
            factors.append({
                "type": "negative",
                "label": "Limited sponsor history",
                "detail": "Sponsor has run few prior trials and no approvals. Execution is unproven.",
            })
    else:
        factors.append({
            "type": "negative",
            "label": "Limited sponsor history",
            "detail": "Insufficient historical trial data for this sponsor - execution risk is hard to assess.",
        })

    # ── Indication difficulty ──────────────────────────────────────
    if indication_rate is not None and phase in ("PHASE1", "PHASE2", "PHASE3"):
        if indication_rate >= 0.5:
            factors.append({
                "type": "positive",
                "label": "Favorable indication",
                "detail": f"{int(indication_rate*100)}% of {phase.replace('PHASE','Phase ')} trials in this indication have historically advanced.",
            })
        elif indication_rate < 0.15:
            factors.append({
                "type": "negative",
                "label": "Difficult indication",
                "detail": f"Only {int(indication_rate*100)}% of {phase.replace('PHASE','Phase ')} trials in this indication historically advance - this is a graveyard area.",
            })

    # ── Sponsor financial resources (market cap proxy) ─────────────
    if market_cap is not None:
        if market_cap >= 10_000_000_000:
            factors.append({
                "type": "positive",
                "label": "Large-cap sponsor",
                "detail": "Major pharma / biotech with deep resources to fund trial completion and commercialization.",
            })
        elif market_cap < 150_000_000 and phase in ("PHASE2", "PHASE3"):
            factors.append({
                "type": "negative",
                "label": "Micro-cap sponsor",
                "detail": "Small-cap companies face financing risk. Late-phase trials are expensive and cash runway matters.",
            })

    # ── Phase (mild signal) ────────────────────────────────────────
    if phase == "PHASE3":
        factors.append({
            "type": "positive",
            "label": "Phase 3",
            "detail": "Drug has already cleared Phase 1 safety and Phase 2 efficacy - it's been meaningfully de-risked.",
        })

    return factors


def _count(factors):
    pos = sum(1 for f in factors if f["type"] == "positive")
    neg = sum(1 for f in factors if f["type"] == "negative")
    return {"positive": pos, "negative": neg}


# ─── Endpoints ───────────────────────────────────────────────────────────


@router.get("/trial/{nct_id}")
async def get_trial_factors(nct_id: str, db: AsyncSession = Depends(get_db)):
    """Return the full factor list for one trial."""
    nct = nct_id.upper()
    result = await db.execute(
        text("""SELECT t.nct_id, t.phase, t.indication, t.overall_status,
                       t.why_stopped, t.has_results, t.enrollment,
                       t.company_ticker, c.market_cap
                FROM trials t
                LEFT JOIN companies c ON c.ticker = t.company_ticker
                WHERE t.nct_id = :nct"""),
        {"nct": nct},
    )
    row = result.fetchone()
    if not row:
        return {"nct_id": nct_id, "scored": False, "factors": []}

    trial = {
        "nct_id": row[0],
        "phase": row[1],
        "indication": row[2],
        "overall_status": row[3],
        "why_stopped": row[4],
        "has_results": row[5],
        "enrollment": row[6],
        "company_ticker": row[7],
    }
    market_cap = row[8]

    # Sponsor track record (if any)
    sponsor = None
    if trial["company_ticker"]:
        sp = await db.execute(
            text("""SELECT total_trials, approval_count, overall_success_rate
                    FROM sponsor_track_records
                    WHERE company_ticker = :t"""),
            {"t": trial["company_ticker"]},
        )
        r = sp.fetchone()
        if r:
            sponsor = {
                "total_trials": r[0],
                "approval_count": r[1],
                "overall_success_rate": r[2],
            }

    # Historical success rate for this indication × phase
    indication_rate = None
    if trial["indication"] and trial["phase"]:
        ir = await db.execute(
            text("""SELECT success_rate
                    FROM indication_success_rates
                    WHERE indication = :ind AND phase = :ph"""),
            {"ind": trial["indication"], "ph": trial["phase"]},
        )
        r = ir.fetchone()
        if r:
            indication_rate = r[0]

    factors = _compute_factors(trial, sponsor, indication_rate, market_cap)
    return {
        "nct_id": nct,
        "scored": True,
        "factors": factors,
        "counts": _count(factors),
    }


@router.get("/batch")
async def get_trial_factors_batch(
    ids: str = Query(..., description="Comma-separated NCT IDs"),
    db: AsyncSession = Depends(get_db),
):
    """Return factor counts (positive / negative) per trial for list views.

    Only returns summary counts - callers fetch the full list per-trial if needed.
    One SQL pass for all trials + bulk lookups for sponsors and indications.
    """
    nct_list = [n.strip().upper() for n in ids.split(",") if n.strip()][:200]
    if not nct_list:
        return {"predictions": {}}

    # Fetch all trials in one go
    result = await db.execute(
        text("""SELECT t.nct_id, t.phase, t.indication, t.overall_status,
                       t.why_stopped, t.has_results, t.enrollment,
                       t.company_ticker, c.market_cap
                FROM trials t
                LEFT JOIN companies c ON c.ticker = t.company_ticker
                WHERE t.nct_id = ANY(:ids)"""),
        {"ids": nct_list},
    )
    rows = result.fetchall()
    if not rows:
        return {"predictions": {}}

    # Gather the unique sponsors + (indication, phase) pairs we'll need
    tickers = {r[7] for r in rows if r[7]}
    ind_phase_pairs = {(r[2], r[1]) for r in rows if r[2] and r[1]}

    # Bulk sponsor lookup
    sponsors = {}
    if tickers:
        sp = await db.execute(
            text("""SELECT company_ticker, total_trials, approval_count, overall_success_rate
                    FROM sponsor_track_records
                    WHERE company_ticker = ANY(:t)"""),
            {"t": list(tickers)},
        )
        for r in sp.fetchall():
            sponsors[r[0]] = {
                "total_trials": r[1],
                "approval_count": r[2],
                "overall_success_rate": r[3],
            }

    # Bulk indication-phase lookup. We fetch the Cartesian product of the
    # unique indications and phases we need, then filter down to the actual
    # pairs in Python. Cheaper than building a VALUES clause and sidesteps
    # the Postgres unnest-zip footgun.
    ind_rates: dict[tuple, float] = {}
    if ind_phase_pairs:
        unique_inds = list({p[0] for p in ind_phase_pairs})
        unique_phases = list({p[1] for p in ind_phase_pairs})
        ir = await db.execute(
            text("""SELECT indication, phase, success_rate
                    FROM indication_success_rates
                    WHERE indication = ANY(:i)
                      AND phase = ANY(:p)"""),
            {"i": unique_inds, "p": unique_phases},
        )
        valid_pairs = set(ind_phase_pairs)
        for r in ir.fetchall():
            pair = (r[0], r[1])
            if pair in valid_pairs:
                ind_rates[pair] = r[2]

    predictions = {}
    for r in rows:
        trial = {
            "nct_id": r[0],
            "phase": r[1],
            "indication": r[2],
            "overall_status": r[3],
            "why_stopped": r[4],
            "has_results": r[5],
            "enrollment": r[6],
            "company_ticker": r[7],
        }
        market_cap = r[8]
        sponsor = sponsors.get(trial["company_ticker"]) if trial["company_ticker"] else None
        indication_rate = ind_rates.get((trial["indication"], trial["phase"]))
        factors = _compute_factors(trial, sponsor, indication_rate, market_cap)
        predictions[trial["nct_id"]] = _count(factors)
    return {"predictions": predictions}


@router.get("/sponsor/{ticker}")
async def get_sponsor_track_record(ticker: str, db: AsyncSession = Depends(get_db)):
    """Get a sponsor's historical trial success rates. Used on company pages."""
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
