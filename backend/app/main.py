import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    news,
    short_interest,
    press_releases,
    deals,
    adcom,
    admin,
    congress_trades,
    drug_sales,
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


async def scheduled_news_sync():
    """Pull biotech news RSS feeds every 15 min."""
    try:
        from app.sync.news_sync import sync_news
        async with async_session() as db:
            count = await sync_news(db)
        logger.info(f"Scheduled news sync: {count} items")
    except Exception as e:
        logger.error(f"Scheduled news sync failed: {e}")


async def scheduled_short_interest_sync():
    """Daily FINRA short-sale volume pull (7 business days lookback)."""
    try:
        from app.sync.short_interest_sync import sync_short_interest
        async with async_session() as db:
            count = await sync_short_interest(db, days=7)
        logger.info(f"Scheduled short-interest sync: {count} rows")
    except Exception as e:
        logger.error(f"Scheduled short-interest sync failed: {e}")


async def scheduled_price_history_sync():
    """Daily top-up of historical price candles (last 7 days)."""
    try:
        from app.sync.price_history_sync import sync_price_history
        async with async_session() as db:
            count = await sync_price_history(db, days=7)
        logger.info(f"Scheduled price history sync: {count} candles")
    except Exception as e:
        logger.error(f"Scheduled price history sync failed: {e}")


async def scheduled_patents_sync():
    """Daily patents refresh via PatentsView (top N companies)."""
    try:
        from app.sync.patents_sync import sync_patents
        async with async_session() as db:
            # Process 300 companies per night to spread PatentsView load;
            # full universe rotates every ~3-4 days.
            count = await sync_patents(db, limit_companies=300)
        logger.info(f"Scheduled patents sync: {count} patents")
    except Exception as e:
        logger.error(f"Scheduled patents sync failed: {e}")


async def scheduled_eight_k_pipeline():
    """Parse recent 8-K filings into press_releases + deals tables."""
    try:
        from app.sync.eight_k_pipeline import sync_eight_k_pipeline
        async with async_session() as db:
            count = await sync_eight_k_pipeline(db, limit=100)
        logger.info(f"Scheduled 8-K pipeline: {count} rows")
    except Exception as e:
        logger.error(f"Scheduled 8-K pipeline failed: {e}")


async def scheduled_fda_adcom_sync():
    """Weekly scrape of the FDA AdCom calendar."""
    try:
        from app.sync.fda_adcom_sync import sync_fda_adcom
        async with async_session() as db:
            count = await sync_fda_adcom(db)
        logger.info(f"Scheduled FDA AdCom: {count} meetings")
    except Exception as e:
        logger.error(f"Scheduled FDA AdCom failed: {e}")


async def scheduled_congress_trades_sync():
    """Daily US House PTR ingest."""
    try:
        from app.sync.congress_trades_sync import sync_congress_trades
        async with async_session() as db:
            count = await sync_congress_trades(db)
        logger.info(f"Scheduled congress trades: {count} rows")
    except Exception as e:
        logger.error(f"Scheduled congress trades failed: {e}")


async def scheduled_drug_sales_sync():
    """Weekly Claude-backed drug sales extraction from 10-Ks."""
    try:
        from app.sync.drug_sales_sync import sync_drug_sales
        async with async_session() as db:
            count = await sync_drug_sales(db, limit=25)
        logger.info(f"Scheduled drug sales: {count} rows")
    except Exception as e:
        logger.error(f"Scheduled drug sales failed: {e}")


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
    scheduler.add_job(
        scheduled_news_sync,
        IntervalTrigger(minutes=15),
        id="news_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_short_interest_sync,
        CronTrigger(hour=9, minute=30),  # FINRA files publish overnight
        id="short_interest_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_price_history_sync,
        CronTrigger(hour=23, minute=15),  # post-close top-up
        id="price_history_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_patents_sync,
        CronTrigger(hour=4, minute=0),
        id="patents_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_eight_k_pipeline,
        CronTrigger(hour=1, minute=0),  # after overnight filing_sync
        id="eight_k_pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_fda_adcom_sync,
        CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="fda_adcom_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_congress_trades_sync,
        CronTrigger(hour=8, minute=0),
        id="congress_trades_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_drug_sales_sync,
        CronTrigger(day_of_week="sat", hour=6, minute=0),
        id="drug_sales_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — prices every 30min, filings every 6h, "
        "trials daily, news every 15min"
    )

    yield

    scheduler.shutdown()
    logger.info("Shutting down Biotech Platform API...")


app = FastAPI(
    title="Biotech Research Platform",
    description="Biotech investing research and analytics API",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware flow on each request:
#   CORS  ->  RateLimit  ->  Cache  ->  route
#
# Gzip used to live here, but Vercel's edge proxy was corrupting gzipped
# responses coming back through the /proxy/* rewrite (body arrived empty
# when client Accept-Encoding was gzip). Vercel compresses at the edge
# anyway (brotli + zstd), so we just hand it raw JSON and let the edge
# handle compression. For direct-to-Fly API traffic, uncompressed is
# acceptable — we have no external consumers to optimise for yet.

# 1. Innermost: response cache (stores raw JSON, TTL per route prefix).
app.add_middleware(ResponseCacheMiddleware)

# 2. Rate limit sits above cache so every request is counted,
#    even cache hits.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIASGIMiddleware)

# 3. Outermost: CORS for any direct-to-Fly requests (the Vercel proxy
#    makes CORS irrelevant for browser traffic, but keep this for the
#    rare direct consumer).
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
app.include_router(news.router)
app.include_router(short_interest.router)
app.include_router(press_releases.router)
app.include_router(deals.router)
app.include_router(adcom.router)
app.include_router(admin.router)
app.include_router(congress_trades.router)
app.include_router(drug_sales.router)


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
