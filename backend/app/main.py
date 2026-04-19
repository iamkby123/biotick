import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded
# SlowAPIASGIMiddleware (vs. SlowAPIMiddleware) is the one that enforces
# default_limits globally; the plain one only respects @limiter.limit decorators.
from slowapi.middleware import SlowAPIASGIMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import init_db, async_session
from app.config import FRONTEND_URL
from app.response_cache import ResponseCacheMiddleware, cache_stats
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import (
    companies,
    drugs,
    catalysts,
    filings,
    analyzer,
    options,
    trial_detail,
    competitors,
    edge,
    sync,
    pdufa,
    earnings,
    historical,
    institutional,
    etfs,
    patents,
    predictions,
    stripe_webhook,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# ── Scheduled sync jobs ─────────────────────────────────────────────

async def scheduled_price_update():
    """Update stock prices every 15 minutes during market hours."""
    try:
        from app.sync.finnhub_sync import sync_prices_finnhub
        async with async_session() as db:
            count = await sync_prices_finnhub(db)
        logger.info(f"Scheduled price update: {count} updated")
    except Exception as e:
        logger.error(f"Scheduled price update failed: {e}")


async def scheduled_filing_sync():
    """Sync SEC filings every 6 hours."""
    try:
        from app.sync.filing_sync import sync_filings
        async with async_session() as db:
            count = await sync_filings(db)
        logger.info(f"Scheduled filing sync: {count} filings")
    except Exception as e:
        logger.error(f"Scheduled filing sync failed: {e}")


async def scheduled_trial_catalyst_sync():
    """Sync trials and extract catalysts daily."""
    try:
        from app.sync.trial_sync import sync_all_trials
        from app.sync.catalyst_extractor import extract_catalysts
        from app.sync.sponsor_matcher import match_sponsors
        async with async_session() as db:
            await sync_all_trials(db)
        async with async_session() as db:
            await match_sponsors(db)
        async with async_session() as db:
            await extract_catalysts(db)
        logger.info("Scheduled trial/catalyst sync complete")
    except Exception as e:
        logger.error(f"Scheduled trial/catalyst sync failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Biotech Platform API...")
    await init_db()
    logger.info("Database initialized")

    # Schedule recurring syncs (2-CPU machine can handle these)
    scheduler.add_job(
        scheduled_price_update,
        IntervalTrigger(minutes=30),
        id="price_update",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_filing_sync,
        CronTrigger(hour="*/6", minute=30),
        id="filing_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_trial_catalyst_sync,
        CronTrigger(hour=5, minute=0),
        id="trial_catalyst_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — prices every 30min, filings every 6h, trials daily")

    yield

    scheduler.shutdown()
    logger.info("Shutting down Biotech Platform API...")


app = FastAPI(
    title="Biotech Research Platform",
    description="Biotech investing research and analytics API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Rate limiting ─────────────────────────────────────────────────
# 120 req/min per IP by default. Specific endpoints can tighten further
# with @limiter.limit("10/minute") at the route level.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIASGIMiddleware)

# ── Response cache (in-memory, TTL per route prefix) ──────────────
app.add_middleware(ResponseCacheMiddleware)

# ── Gzip compression for payloads >= 1KB ──────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1024)

# ── CORS (outermost so preflight always works) ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://127.0.0.1:3000",
        "https://frontend-nu-rouge-22.vercel.app",
        "https://biotick.io",
        "https://www.biotick.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(companies.router)
app.include_router(drugs.router)
app.include_router(catalysts.router)
app.include_router(filings.router)
app.include_router(analyzer.router)
app.include_router(options.router)
app.include_router(trial_detail.router)
app.include_router(competitors.router)
app.include_router(edge.router)
app.include_router(sync.router)
app.include_router(pdufa.router)
app.include_router(earnings.router)
app.include_router(historical.router)
app.include_router(institutional.router)
app.include_router(etfs.router)
app.include_router(patents.router)
app.include_router(predictions.router)
app.include_router(stripe_webhook.router)


@app.get("/api/health")
async def health_check():
    db_ok = False
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "biotech-platform",
        "db_connected": db_ok,
        "scheduler_running": scheduler.running,
        "scheduled_jobs": jobs,
        "cache": cache_stats(),
    }
