import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
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
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    # Supabase transaction pooler doesn't support prepared statements
    connect_args={"statement_cache_size": 0},
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
        logger.error(f"Database connection failed: {e}")
        raise


async def get_db():
    """Dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
