from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from sqlmodel import SQLModel

from majlisna.schema import migrate_to_head
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
        settings = Settings()
        return await create_app_engine(settings)
    return _engine


async def dispose_engine() -> None:
    """Dispose the shared engine and reset the singleton (used on app shutdown)."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def create_db_and_tables(engine: AsyncEngine, drop_all: bool = False) -> None:
    """Bring the schema up to date. Idempotent: safe at every boot, from every worker.

    - **PostgreSQL** (production, E2E, a dev database): the Alembic migrations, to head,
      in ONE transaction under ``pg_advisory_xact_lock(SCHEMA_DDL_LOCK_KEY)``
      (``schema.migrate_to_head``). A database created before migrations is adopted once,
      if its schema is the baseline's, else the boot fails (see ``majlisna/schema.py``).
      Every uvicorn worker runs this; the lock makes them take turns, the first migrates
      and the others find the database at head (INFRA-13: without a lock, 3 of 4 workers
      crashed on CREATE TYPE).
    - **SQLite** (dev, the default test run): ``create_all``, which creates the missing
      tables and never ALTERs one. The migrations are written for PostgreSQL only.

    ``drop_all`` drops every table first (and, on PostgreSQL, the version table): only for
    ``scripts/generate_fake_data.py --delete``, which refuses production (PD-02). Nothing
    else here drops anything.
    """
    if engine.dialect.name == "postgresql":
        await migrate_to_head(engine, drop_first=drop_all)
        return
    async with engine.begin() as conn:
        if drop_all:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        # SQLite FK enforcement is per-connection and is set by the pool "connect"
        # listener installed in create_app_engine — a PRAGMA issued here would only
        # apply to this one connection.


async def create_schema(settings: Settings, app_engine: AsyncEngine) -> None:
    """The app's schema at boot: ``create_db_and_tables`` over the direct PostgreSQL connection.

    ``DIRECT_DATABASE_URL`` bypasses PgBouncer, like the admin scripts: DDL through
    PgBouncer's transaction pooling leaves pooled server connections with a stale asyncpg
    type cache (see ``Settings.direct_database_url``). A throwaway engine, disposed once the
    schema is at head. Without a direct URL (SQLite dev, a stack with no PgBouncer) the app's
    own engine does it — the advisory lock is transaction-scoped, so it holds either way.
    """
    if not settings.direct_database_url:
        await create_db_and_tables(app_engine)
        return
    ddl_engine = create_async_engine(settings.direct_database_url, poolclass=NullPool)
    try:
        await create_db_and_tables(ddl_engine)
    finally:
        await ddl_engine.dispose()
