from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel import SQLModel

from majlisna.settings import Settings

_engine: AsyncEngine | None = None


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """Turn on SQLite foreign-key enforcement for EVERY pooled connection.

    SQLite disables FK checks per connection by default. This used to be a single
    ``PRAGMA foreign_keys=ON`` issued on the one connection that created the
    tables, which does not carry over to any other connection in the pool — so
    dev and the whole test suite ran with foreign keys effectively OFF. That is
    exactly the class of bug the user-deletion purge logic exists to prevent, and
    the tests covering it could never have caught a regression.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def create_app_engine(settings: Settings) -> AsyncEngine:
    """Create (once) the async database engine with connection pooling.

    Stores the result in the module-level singleton so that the app lifespan
    and the request dependencies share a SINGLE engine/pool. Previously the
    lifespan created its own engine while `get_engine()` created a second one,
    doubling the connection pool and leaking the second on shutdown.
    """
    global _engine  # noqa: PLW0603
    if _engine is not None:
        return _engine

    connect_args = {}
    if "postgresql" in settings.database_url:
        connect_args["prepared_statement_cache_size"] = 0  # Required for PgBouncer transaction pooling

    _engine = create_async_engine(
        settings.database_url,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        connect_args=connect_args,
    )
    if "sqlite" in settings.database_url:
        _enable_sqlite_foreign_keys(_engine)
    return _engine


async def get_engine() -> AsyncEngine:
    """Get or create the shared database engine singleton."""
    if _engine is None:
        settings = Settings()  # type: ignore
        return await create_app_engine(settings)
    return _engine


async def dispose_engine() -> None:
    """Dispose the shared engine and reset the singleton (used on app shutdown)."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def create_db_and_tables(engine: AsyncEngine, drop_all: bool = False) -> None:
    """Create all database tables.

    NOTE: `create_all` only CREATEs missing tables — it never ALTERs an existing
    one. Schema changes to a table that already exists on a server are applied by
    dropping and reseeding the database (`scripts/generate_fake_data.py --delete`
    then `--create-db`), not by migrations.
    """
    async with engine.begin() as conn:
        if drop_all:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        if "postgresql" in str(engine.url):
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_game_live_state_gin ON game USING GIN (live_state)"))
        # SQLite FK enforcement is per-connection and is set by the pool "connect"
        # listener installed in create_app_engine — a PRAGMA issued here would only
        # apply to this one connection.
