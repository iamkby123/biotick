import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.config import FRONTEND_URL
from app.routers import companies, drugs, catalysts, filings, analyzer, options, trial_detail, competitors, edge, sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Biotech Platform API...")
    await init_db()
    logger.info("Database initialized")
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


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "biotech-platform"}
