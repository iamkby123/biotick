import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import DATABASE_URL, DATA_DIR

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Log the connection target (hide password)
_safe_url = DATABASE_URL
if "@" in _safe_url:
    _safe_url = _safe_url.split("@")[0].rsplit(":", 1)[0] + ":***@" + _safe_url.split("@")[1]
logger.info(f"Database URL: {_safe_url}")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    # NullPool required for Supabase transaction-mode pooler (port 6543)
    poolclass=NullPool,
    connect_args={
        "prepare_threshold": 0,  # disable prepared statements for transaction pooler
    },
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Verify database connection (tables managed by Supabase migrations)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        # Don't crash the app — let it start so we can diagnose via /api/health
        logger.error(f"Database connection failed (app will start anyway): {e}")


async def get_db():
    """Dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
