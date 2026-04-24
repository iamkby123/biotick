import asyncio
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import require_admin_key
from app.database import get_db, async_session
from app.models.sync_log import SyncLog
from app.sync.company_sync import sync_companies, enrich_companies_with_sic
from app.sync.market_data_sync import sync_market_data, sync_company_info
from app.sync.trial_sync import sync_all_trials
from app.sync.catalyst_extractor import extract_catalysts
from app.sync.filing_sync import sync_filings
from app.sync.bulk_trial_sync import bulk_download_trials
from app.sync.sponsor_matcher import match_sponsors
from app.sync.company_info_sync import sync_company_info_from_edgar
from app.sync.description_generator import generate_descriptions
from app.sync.finnhub_sync import sync_prices_finnhub, sync_financials_finnhub
from app.sync.drug_normalizer import normalize_all_drugs
from app.sync.fda_calendar_sync import sync_fda_approvals
from app.sync.sec_financials_sync import sync_sec_financials
# Phase A-D data expansion syncs
from app.sync.news_sync import sync_news
from app.sync.short_interest_sync import sync_short_interest
from app.sync.patents_sync import sync_patents
from app.sync.price_history_sync import sync_price_history
from app.sync.eight_k_pipeline import sync_eight_k_pipeline
from app.sync.fda_adcom_sync import sync_fda_adcom
from app.sync.congress_trades_sync import sync_congress_trades
from app.sync.drug_sales_sync import sync_drug_sales
from app.sync.drug_pipeline_sync import sync_drug_pipelines

logger = logging.getLogger(__name__)

# Every route in this router is gated by X-Admin-Key. These endpoints
# trigger expensive data refreshes (SEC EDGAR, Finnhub, Anthropic) and
# were previously wide open — any random visitor could force-run them
# and rack up API bills. Lock them all at the router level.
router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
    dependencies=[Depends(require_admin_key)],
)

# Track running sync jobs
_running_syncs: set[str] = set()


async def _run_sync_in_background(sync_type: str, sync_fn, **kwargs):
    """Run a sync function with its own database session."""
    if sync_type in _running_syncs:
        logger.warning(f"Sync {sync_type} already running, skipping")
        return
    _running_syncs.add(sync_type)
    try:
        async with async_session() as db:
            await sync_fn(db, **kwargs)
    except Exception as e:
        logger.error(f"Background sync {sync_type} failed: {e}")
    finally:
        _running_syncs.discard(sync_type)


@router.post("/companies")
async def trigger_company_sync(db: AsyncSession = Depends(get_db)):
    """Trigger company list sync from SEC EDGAR. Runs inline (fast)."""
    count = await sync_companies(db)
    return {"status": "completed", "companies_synced": count}


@router.post("/companies/enrich-sic")
async def trigger_sic_enrichment(background_tasks: BackgroundTasks):
    """Enrich companies with SIC codes. Runs in background (slow)."""
    if "COMPANIES_SIC" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "COMPANIES_SIC", enrich_companies_with_sic)
    return {"status": "started", "message": "SIC enrichment started in background. Check /api/sync/status for progress."}


@router.post("/market-data")
async def trigger_market_data_sync(background_tasks: BackgroundTasks):
    """Trigger price/market data update. Runs in background (slow)."""
    if "MARKET_DATA" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "MARKET_DATA", sync_market_data)
    return {"status": "started", "message": "Market data sync started in background. Check /api/sync/status for progress."}


@router.post("/trials")
async def trigger_trial_sync(background_tasks: BackgroundTasks):
    """Sync clinical trials from ClinicalTrials.gov. Runs in background."""
    if "TRIALS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "TRIALS", sync_all_trials)
    return {"status": "started", "message": "Trial sync started in background. Check /api/sync/status for progress."}


@router.post("/bulk-trials")
async def trigger_bulk_trial_sync(background_tasks: BackgroundTasks):
    """Bulk download all interventional trials from ClinicalTrials.gov. Runs in background."""
    if "BULK_TRIALS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "BULK_TRIALS", bulk_download_trials)
    return {"status": "started", "message": "Bulk trial import started in background. This may take several minutes."}


@router.post("/sponsor-match")
async def trigger_sponsor_matching(background_tasks: BackgroundTasks):
    """Match trial sponsors to companies using fuzzy matching. Runs in background."""
    if "SPONSOR_MATCH" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "SPONSOR_MATCH", match_sponsors)
    return {"status": "started", "message": "Sponsor matching started in background."}


@router.post("/descriptions")
async def trigger_description_generation(background_tasks: BackgroundTasks):
    """Auto-generate company descriptions from pipeline data."""
    if "DESCRIPTIONS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "DESCRIPTIONS", generate_descriptions)
    return {"status": "started", "message": "Description generation started."}


@router.post("/prices")
async def trigger_finnhub_prices(background_tasks: BackgroundTasks):
    """Fetch prices from Finnhub.io. Runs in background (~15 min for all companies)."""
    if "PRICES_FINNHUB" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "PRICES_FINNHUB", sync_prices_finnhub)
    return {"status": "started", "message": "Finnhub price sync started. Takes ~15 min for all companies."}


@router.post("/financials")
async def trigger_finnhub_financials(background_tasks: BackgroundTasks):
    """Fetch financials (beta, PE, 52w range, etc.) from Finnhub. ~15 min."""
    if "FINANCIALS_FINNHUB" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "FINANCIALS_FINNHUB", sync_financials_finnhub)
    return {"status": "started", "message": "Finnhub financials sync started. Takes ~15 min."}


@router.post("/normalize-drugs")
async def trigger_drug_normalization(background_tasks: BackgroundTasks):
    """Normalize drug names — strip dosages, mark placebos. Runs in background."""
    if "DRUG_NORMALIZE" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "DRUG_NORMALIZE", normalize_all_drugs)
    return {"status": "started", "message": "Drug normalization started."}


@router.post("/fda-approvals")
async def trigger_fda_sync(background_tasks: BackgroundTasks):
    """Fetch FDA approval dates from OpenFDA. Runs in background."""
    if "FDA_APPROVALS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "FDA_APPROVALS", sync_fda_approvals)
    return {"status": "started", "message": "FDA approval sync started."}


@router.post("/sec-financials")
async def trigger_sec_financials(background_tasks: BackgroundTasks):
    """Fill in revenue, shares, employees from SEC EDGAR XBRL. No API key needed."""
    if "SEC_FINANCIALS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "SEC_FINANCIALS", sync_sec_financials)
    return {"status": "started", "message": "SEC financials sync started."}


@router.post("/company-info-edgar")
async def trigger_edgar_company_info(background_tasks: BackgroundTasks):
    """Enrich companies with address/phone from SEC EDGAR. Runs in background."""
    if "COMPANY_INFO_EDGAR" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "COMPANY_INFO_EDGAR", sync_company_info_from_edgar)
    return {"status": "started", "message": "Company info sync from EDGAR started in background."}


@router.post("/catalysts")
async def trigger_catalyst_extraction(background_tasks: BackgroundTasks):
    """Extract catalysts from trial data. Runs in background."""
    if "CATALYSTS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "CATALYSTS", extract_catalysts)
    return {"status": "started", "message": "Catalyst extraction started in background."}


@router.post("/filings")
async def trigger_filing_sync(background_tasks: BackgroundTasks):
    """Sync SEC filings and insider trades. Runs in background."""
    if "FILINGS" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "FILINGS", sync_filings)
    return {"status": "started", "message": "Filing sync started in background."}


@router.post("/company-info")
async def trigger_company_info_sync(
    limit: int = 50,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Enrich companies with detailed info from yfinance. Runs in background."""
    if "COMPANY_INFO" in _running_syncs:
        return {"status": "already_running"}
    background_tasks.add_task(_run_sync_in_background, "COMPANY_INFO", sync_company_info, limit=limit)
    return {"status": "started", "message": "Company info sync started in background."}


@router.post("/full")
async def trigger_full_sync(background_tasks: BackgroundTasks):
    """Run all syncs in sequence to fully populate the database."""
    if "FULL_SYNC" in _running_syncs:
        return {"status": "already_running"}

    async def _full_sync():
        """Run all syncs in the correct order."""
        _running_syncs.add("FULL_SYNC")
        try:
            logger.info("Full sync: starting company sync...")
            async with async_session() as db:
                await sync_companies(db)
            logger.info("Full sync: companies done")

            logger.info("Full sync: enriching SIC codes...")
            async with async_session() as db:
                await enrich_companies_with_sic(db)
            logger.info("Full sync: SIC done")

            logger.info("Full sync: company info from EDGAR...")
            async with async_session() as db:
                await sync_company_info_from_edgar(db)
            logger.info("Full sync: company info done")

            logger.info("Full sync: generating descriptions...")
            async with async_session() as db:
                await generate_descriptions(db)
            logger.info("Full sync: descriptions done")

            logger.info("Full sync: bulk trial download...")
            async with async_session() as db:
                await bulk_download_trials(db)
            logger.info("Full sync: bulk trials done")

            logger.info("Full sync: sponsor matching...")
            async with async_session() as db:
                await match_sponsors(db)
            logger.info("Full sync: sponsor matching done")

            logger.info("Full sync: extracting catalysts...")
            async with async_session() as db:
                await extract_catalysts(db)
            logger.info("Full sync: catalysts done")

            logger.info("Full sync: syncing filings...")
            async with async_session() as db:
                await sync_filings(db)
            logger.info("Full sync: filings done")

            logger.info("Full sync: SEC financials...")
            async with async_session() as db:
                await sync_sec_financials(db)
            logger.info("Full sync: SEC financials done")

            logger.info("Full sync: Finnhub prices...")
            async with async_session() as db:
                await sync_prices_finnhub(db)
            logger.info("Full sync: prices done")

            logger.info("Full sync: FDA approvals...")
            async with async_session() as db:
                await sync_fda_approvals(db)
            logger.info("Full sync: ALL COMPLETE")

        except Exception as e:
            logger.error(f"Full sync failed: {e}")
        finally:
            _running_syncs.discard("FULL_SYNC")

    background_tasks.add_task(_full_sync)
    return {
        "status": "started",
        "message": "Full database sync started. This will take 30-60 minutes. Check /api/sync/status for progress.",
    }


@router.get("/status")
async def get_sync_status(db: AsyncSession = Depends(get_db)):
    """Get the last sync status for each sync type."""
    result = await db.execute(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(20)
    )
    logs = result.scalars().all()

    # Group by sync_type, keep latest
    latest: dict = {}
    for log in logs:
        if log.sync_type not in latest:
            latest[log.sync_type] = {
                "sync_type": log.sync_type,
                "status": log.status,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "records_processed": log.records_processed,
                "error_message": log.error_message,
            }

    return {
        "syncs": list(latest.values()),
        "currently_running": list(_running_syncs),
    }


# ── Phase A-D admin triggers ─────────────────────────────────────────
# Each of the new syncs gets a POST endpoint so we can kick off the
# initial backfill without waiting for the nightly cron.
#
# NOTE: we use asyncio.create_task instead of FastAPI's BackgroundTasks
# because SlowAPI's ASGI middleware conflicts with BackgroundTasks and
# kills the task before it can write to sync_log. create_task schedules
# the coroutine on the event loop independently of the HTTP response.

def _fire(sync_type: str, coro_factory):
    """Schedule a sync to run after this request returns."""
    if sync_type in _running_syncs:
        return {"status": "already_running"}
    asyncio.create_task(coro_factory())
    return {"status": "started"}


async def _wrap(sync_type: str, sync_fn, **kwargs):
    """Same shape as _run_sync_in_background but suitable for create_task."""
    if sync_type in _running_syncs:
        logger.warning(f"Sync {sync_type} already running, skipping")
        return
    _running_syncs.add(sync_type)
    try:
        async with async_session() as db:
            await sync_fn(db, **kwargs)
    except Exception as e:
        logger.exception(f"Background sync {sync_type} failed: {e}")
    finally:
        _running_syncs.discard(sync_type)


@router.post("/news")
async def trigger_news_sync():
    result = _fire("NEWS", lambda: _wrap("NEWS", sync_news))
    return {**result, "message": "News RSS sync started."}


@router.post("/short-interest")
async def trigger_short_interest(days: int = 14):
    result = _fire(
        "SHORT_INTEREST",
        lambda: _wrap("SHORT_INTEREST", sync_short_interest, days=days),
    )
    return {**result, "message": f"FINRA short-interest backfill ({days}d) started."}


@router.post("/patents")
async def trigger_patents(limit_companies: int = 200):
    result = _fire(
        "PATENTS",
        lambda: _wrap("PATENTS", sync_patents, limit_companies=limit_companies),
    )
    return {
        **result,
        "message": f"Lens.org patents backfill started ({limit_companies} companies).",
    }


@router.post("/price-history")
async def trigger_price_history(days: int = 365):
    """Backfill OHLCV candles. Pass days=1825 for full 5y backfill."""
    result = _fire(
        "PRICE_HISTORY",
        lambda: _wrap("PRICE_HISTORY", sync_price_history, days=days),
    )
    return {**result, "message": f"Finnhub price-history backfill ({days}d) started."}


@router.post("/eight-k")
async def trigger_eight_k_pipeline(limit: int = 200):
    """Parse 8-K filings into press_releases + deals. ANTHROPIC_API_KEY
    must be set for summaries; otherwise rows get raw-text bodies only."""
    result = _fire(
        "EIGHT_K_PIPELINE",
        lambda: _wrap("EIGHT_K_PIPELINE", sync_eight_k_pipeline, limit=limit),
    )
    return {**result, "message": f"8-K pipeline backfill ({limit} filings) started."}


@router.post("/fda-adcom")
async def trigger_fda_adcom():
    result = _fire("FDA_ADCOM", lambda: _wrap("FDA_ADCOM", sync_fda_adcom))
    return {**result, "message": "FDA Advisory Committee calendar scrape started."}


@router.post("/congress-trades")
async def trigger_congress_trades():
    result = _fire(
        "CONGRESS_TRADES", lambda: _wrap("CONGRESS_TRADES", sync_congress_trades)
    )
    return {**result, "message": "US House PTR ingest started."}


@router.post("/drug-sales")
async def trigger_drug_sales(limit: int = 25):
    """Claude-backed extraction from 10-Ks. Costs ~$0.03 per filing."""
    result = _fire(
        "DRUG_SALES",
        lambda: _wrap("DRUG_SALES", sync_drug_sales, limit=limit),
    )
    return {
        **result,
        "message": f"Drug-sales extraction started ({limit} 10-Ks, ~${limit * 0.03:.2f} budget).",
    }


@router.post("/drug-pipelines")
async def trigger_drug_pipelines(limit: int = 30, min_market_cap: int = 500_000_000):
    """Claude-backed pipeline extraction from 10-K / 20-F for companies
    with <5 drugs in our database. Costs ~$0.03 per filing."""
    result = _fire(
        "DRUG_PIPELINE",
        lambda: _wrap(
            "DRUG_PIPELINE",
            sync_drug_pipelines,
            limit=limit,
            min_market_cap=min_market_cap,
        ),
    )
    return {
        **result,
        "message": f"Drug pipeline enrichment started ({limit} filings, ~${limit * 0.03:.2f} budget).",
    }
