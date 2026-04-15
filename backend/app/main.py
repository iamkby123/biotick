import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.config import FRONTEND_URL
from app.routers import companies, drugs, catalysts, filings, analyzer, options, trial_detail, competitors, edge, sync, pdufa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def auto_sync_if_empty():
    """Auto-run syncs if database is empty (fresh deploy)."""
    from sqlalchemy import select, func
    from app.database import async_session
    from app.models.company import Company

    async with async_session() as db:
        result = await db.execute(select(func.count()).select_from(Company))
        count = result.scalar() or 0

    if count == 0:
        logger.info("Empty database detected — running auto-sync...")
        from app.sync.company_sync import sync_companies, enrich_companies_with_sic
        from app.sync.bulk_trial_sync import bulk_download_trials
        from app.sync.description_generator import generate_descriptions
        from app.sync.company_info_sync import sync_company_info_from_edgar
        from app.sync.filing_sync import sync_filings
        from app.sync.sec_financials_sync import sync_sec_financials

        async with async_session() as db:
            await sync_companies(db)
            logger.info("Auto-sync: companies done")

        # Run the rest in background
        import asyncio

        async def background_syncs():
            async with async_session() as db:
                await enrich_companies_with_sic(db)
                logger.info("Auto-sync: SIC enrichment done")
            async with async_session() as db:
                await generate_descriptions(db)
            async with async_session() as db:
                await sync_company_info_from_edgar(db)
            async with async_session() as db:
                await bulk_download_trials(db)
            async with async_session() as db:
                await sync_filings(db)
            async with async_session() as db:
                await sync_sec_financials(db)
            logger.info("Auto-sync: all background syncs complete")

        asyncio.create_task(background_syncs())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Biotech Platform API...")
    await init_db()
    logger.info("Database initialized")
    await auto_sync_if_empty()
    yield
    logger.info("Shutting down Biotech Platform API...")


app = FastAPI(
    title="Biotech Research Platform",
    description="Biotech investing research and analytics API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - allow frontend
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


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "biotech-platform"}
