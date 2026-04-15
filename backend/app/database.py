from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import DATABASE_URL, DATA_DIR


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Verify database connection (tables managed by Supabase migrations)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def get_db():
    """Dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
