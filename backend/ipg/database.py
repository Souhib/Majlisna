from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel import SQLModel

from ipg.settings import Settings

_engine: AsyncEngine | None = None


async def create_app_engine(settings: Settings) -> AsyncEngine:
    """Create an async database engine with connection pooling."""
    engine = create_async_engine(
        settings.database_url,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=20,
        max_overflow=30,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
    )
    return engine


async def get_engine() -> AsyncEngine:
    """Get or create the database engine singleton."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = Settings()  # type: ignore
        _engine = await create_app_engine(settings)
    return _engine


async def create_db_and_tables(engine: AsyncEngine, drop_all: bool = False) -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        if drop_all:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        if "postgresql" in str(engine.url):
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_game_live_state_gin ON game USING GIN (live_state)"))
        elif "sqlite" in str(engine.url):
            await conn.execute(text("PRAGMA foreign_keys=ON"))
