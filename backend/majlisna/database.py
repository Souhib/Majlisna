from typing import NamedTuple

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from sqlmodel import SQLModel

from majlisna.api.constants import SCHEMA_DDL_LOCK_KEY, SCHEMA_DDL_LOCK_TIMEOUT
from majlisna.settings import Settings

_engine: AsyncEngine | None = None


class PostgresIndex(NamedTuple):
    """An index the models cannot declare (an expression, a sort order), PostgreSQL only."""

    name: str
    create: str


# Created at boot when missing. Each one is OPTIONAL: if it cannot be built (a
# case-variant duplicate already stored, its table lock not granted within
# SCHEMA_DDL_LOCK_TIMEOUT) the boot logs an error and goes on without it, and the next
# boot tries again. A unique index must never be what keeps production down.
POSTGRES_INDEXES: tuple[PostgresIndex, ...] = (
    # Usernames are unique case-insensitively: the backstop behind username_claim_lock,
    # and what username_is_taken's `lower(username) = lower(:name)` reads (BDP-12).
    PostgresIndex(
        "ix_user_username_lower",
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_username_lower ON "user" (lower(username))',
    ),
    # One account per mailbox, whatever the case (SEC-F14). email_address's own unique
    # constraint compares exactly, so "Ali@x.com" and "ali@x.com" were two accounts.
    PostgresIndex(
        "ix_user_email_lower",
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email_lower ON "user" (lower(email_address))',
    ),
    # Account deletion purges the user's chat messages: a sequential scan without it.
    PostgresIndex(
        "ix_chatmessage_user_id",
        "CREATE INDEX IF NOT EXISTS ix_chatmessage_user_id ON chatmessage (user_id)",
    ),
    # The leaderboard: ORDER BY total_games_won DESC LIMIT n.
    PostgresIndex(
        "ix_userstats_total_games_won_desc",
        "CREATE INDEX IF NOT EXISTS ix_userstats_total_games_won_desc ON userstats (total_games_won DESC)",
    ),
)

# Dropped at boot when present: never read, yet maintained on every write of their table.
# - ix_game_live_state_gin: a GIN index on game.live_state, which no query reads with a
#   JSONB operator (idx_scan 0 in production; PD-16). The old boot created it.
# - ix_roomuserlink_room_id: a prefix of uq_roomuserlink_room_user (BDP-12). The model
#   declared it until WP-21.
POSTGRES_DROPPED_INDEXES: tuple[str, ...] = ("ix_game_live_state_gin", "ix_roomuserlink_room_id")


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
    """Create what the schema is missing. Additive and idempotent: safe at every boot.

    - ``create_all`` creates every missing table, with its enums and indexes. It never
      ALTERs an existing table, so a schema change is a NEW table (or an index below),
      never a new column on an old one.
    - On PostgreSQL, the indexes the models cannot declare (``POSTGRES_INDEXES``) are
      created when missing and the unused ones (``POSTGRES_DROPPED_INDEXES``) dropped
      when present — each optional, see ``_apply_postgres_indexes``.

    Every uvicorn worker runs this in its lifespan. On PostgreSQL it all happens in ONE
    transaction under ``pg_advisory_xact_lock(SCHEMA_DDL_LOCK_KEY)``, so the workers take
    turns: the first creates, the others find everything there. Without the lock they
    raced on CREATE TYPE / CREATE TABLE and 3 of 4 crashed at boot (INFRA-13, PD-13).
    The lock is transaction-scoped (released by the commit or the rollback; never a
    session lock, which leaks when a pooled connection is recycled). The app sends this
    over the direct connection, not PgBouncer (``create_schema``).

    Nothing here drops a table or a column, and nobody needs to drop and reseed a server
    to change its schema: that sequence once wiped production (PD-02). ``drop_all`` is
    only for ``scripts/generate_fake_data.py --delete``, which refuses production. A
    release that changes the schema still takes a ``pg_dump`` of production first.
    """
    is_postgres = engine.dialect.name == "postgresql"
    async with engine.begin() as conn:
        if is_postgres:
            # Blocking, before any DDL: a worker that waits here then sees, through fresh
            # READ COMMITTED snapshots, everything the one before it committed.
            await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCHEMA_DDL_LOCK_KEY})
        if drop_all:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        if is_postgres:
            await _apply_postgres_indexes(conn)
        # SQLite FK enforcement is per-connection and is set by the pool "connect"
        # listener installed in create_app_engine — a PRAGMA issued here would only
        # apply to this one connection.


async def _apply_postgres_indexes(conn: AsyncConnection) -> None:
    """Create the ``POSTGRES_INDEXES`` missing, drop the ``POSTGRES_DROPPED_INDEXES`` present.

    Only the statements needed run, so a boot with nothing to change takes no table lock
    (CREATE INDEX IF NOT EXISTS locks its table before it checks). Each statement runs
    in its own savepoint under ``SCHEMA_DDL_LOCK_TIMEOUT``: a failure rolls back that
    statement alone and is logged, never the tables created before it, never the boot.
    """
    rows = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"))
    present = set(rows.scalars())
    # Transaction-local (is_local), set after the advisory lock so the wait for that is
    # not bounded: the other workers must wait for the whole schema, however long.
    await conn.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": SCHEMA_DDL_LOCK_TIMEOUT})
    for index in POSTGRES_INDEXES:
        if index.name not in present:
            await _run_optional_ddl(conn, index.name, index.create)
    # Last: a DROP INDEX holds an ACCESS EXCLUSIVE lock on its table (reads too) until
    # the commit, so no other statement waits for a lock while the table is closed.
    for name in POSTGRES_DROPPED_INDEXES:
        if name in present:
            await _run_optional_ddl(conn, name, f'DROP INDEX IF EXISTS "{name}"')


async def _run_optional_ddl(conn: AsyncConnection, name: str, statement: str) -> None:
    """Run one optional DDL statement in a savepoint; on failure log it and go on.

    The log names the index and PostgreSQL's first line, not its DETAIL, which quotes the
    duplicated value (a username or an email address).
    """
    try:
        async with conn.begin_nested():
            await conn.execute(text(statement))
    except DBAPIError as exc:
        reason = str(exc.orig).splitlines()[0] if exc.orig is not None else type(exc).__name__
        logger.error(
            "Startup DDL: {} skipped, the server runs without it until a boot succeeds ({}). "
            "For a unique index, look for case-variant duplicates of its column first.",
            name,
            reason,
        )


async def create_schema(settings: Settings, app_engine: AsyncEngine) -> None:
    """The app's startup DDL: ``create_db_and_tables`` over the direct PostgreSQL connection.

    ``DIRECT_DATABASE_URL`` bypasses PgBouncer, like the admin scripts: DDL through
    PgBouncer's transaction pooling leaves pooled server connections with a stale asyncpg
    type cache (see ``Settings.direct_database_url``). A throwaway engine, disposed once the
    schema is there. Without a direct URL (SQLite dev, a stack with no PgBouncer) the app's
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
