"""Startup DDL on PostgreSQL: run once under a lock, and the indexes it keeps (WP-21).

Every uvicorn worker runs ``create_db_and_tables`` in its lifespan. Four of them on a
database missing a table or an enum used to race on ``CREATE TYPE`` / ``CREATE TABLE``,
and three of the four crashed with a UniqueViolation (INFRA-13, PD-13, BDP-11). The
same function now also keeps the indexes the models cannot declare (BDP-12, PD-16,
SEC-F14).

Each test runs against a database of its own, created for it in the session's
PostgreSQL container: the unique ``lower()`` indexes must never reach the shared test
database, where other tests store case variants on purpose.
"""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.table import User
from majlisna.database import create_db_and_tables, create_schema
from majlisna.settings import Settings

pytestmark = pytest.mark.postgres

# UVICORN_WORKERS in backend/Dockerfile.
CONCURRENT_BOOTS = 4

# Far above SCHEMA_DDL_LOCK_TIMEOUT (5 s) per waiting statement: a boot that takes longer
# behind a held table lock is a boot that would have waited for it forever.
BOOT_DEADLINE_SECONDS = 30

# Nothing listens on the discard port: an engine on this URL fails at its first connect.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://nobody:nothing@127.0.0.1:9/unreachable"

# What the previous code left on every server: the GIN index it created at each boot,
# and the index ``RoomUserLink.room_id`` declared (a prefix of uq_roomuserlink_room_user).
LEGACY_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS ix_game_live_state_gin ON game USING GIN (live_state)",
    "CREATE INDEX IF NOT EXISTS ix_roomuserlink_room_id ON roomuserlink (room_id)",
)
DROPPED_INDEXES = {"ix_game_live_state_gin", "ix_roomuserlink_room_id"}
KEPT_INDEXES = {
    "ix_user_username_lower",
    "ix_user_email_lower",
    "ix_chatmessage_user_id",
    "ix_userstats_total_games_won_desc",
}


# ========== Helpers ==========


@pytest_asyncio.fixture(name="fresh_database_url")
async def get_fresh_database_url(postgres_container) -> AsyncIterator[str]:
    """Create an empty database in the session's container, and drop it afterwards."""
    base_url = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    name = f"wp21_{uuid4().hex}"
    admin = create_async_engine(base_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield f"{base_url.rsplit('/', 1)[0]}/{name}"
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


@pytest_asyncio.fixture(name="fresh_engine")
async def get_fresh_engine(fresh_database_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine on the fresh database, the way a worker's would be (no shared pool)."""
    engine = create_async_engine(fresh_database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


async def _boot(url: str) -> None:
    """One worker's startup: its own engine, then the schema."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        await create_db_and_tables(engine)
    finally:
        await engine.dispose()


async def _create_tables_as_the_previous_code_did(engine: AsyncEngine) -> None:
    """A server booted before this change: every table, plus the legacy indexes."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        for statement in LEGACY_INDEX_DDL:
            await conn.execute(text(statement))


async def _index_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        return {row[0] for row in rows}


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        return {row[0] for row in rows}


def _user(username: str, email_address: str) -> User:
    return User(username=username, email_address=email_address, password="not-a-real-hash")


async def _stored_users(engine: AsyncEngine) -> list[tuple[str, str]]:
    async with AsyncSession(engine) as session:
        rows = await session.exec(select(User.username, User.email_address).order_by(col(User.username)))
        return [(row[0], row[1]) for row in rows.all()]


# ========== Run once ==========


async def test_four_workers_booting_on_a_fresh_schema_all_succeed(fresh_database_url: str, fresh_engine: AsyncEngine):
    # Prepare
    boots = [_boot(fresh_database_url) for _ in range(CONCURRENT_BOOTS)]

    # Act
    results = await asyncio.gather(*boots, return_exceptions=True)

    # Assert
    failures = [repr(result) for result in results if isinstance(result, BaseException)]
    assert failures == []
    assert set(SQLModel.metadata.tables) <= await _table_names(fresh_engine)
    assert KEPT_INDEXES.issubset(await _index_names(fresh_engine))


async def test_a_second_boot_changes_nothing(fresh_engine: AsyncEngine):
    # Prepare
    await create_db_and_tables(fresh_engine)
    indexes_after_first_boot = await _index_names(fresh_engine)

    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    assert await _index_names(fresh_engine) == indexes_after_first_boot


async def test_the_app_creates_its_schema_over_the_direct_connection(
    fresh_database_url: str, fresh_engine: AsyncEngine
):
    # Prepare: DATABASE_URL (PgBouncer in production) cannot be reached, the direct URL can
    settings = Settings(database_url=UNREACHABLE_DATABASE_URL, direct_database_url=fresh_database_url)
    app_engine = create_async_engine(settings.database_url, poolclass=NullPool)

    # Act
    try:
        await create_schema(settings, app_engine)
    finally:
        await app_engine.dispose()

    # Assert
    assert set(SQLModel.metadata.tables) <= await _table_names(fresh_engine)
    assert KEPT_INDEXES.issubset(await _index_names(fresh_engine))


async def test_without_a_direct_url_the_app_engine_creates_the_schema(
    fresh_database_url: str, fresh_engine: AsyncEngine
):
    # Prepare
    settings = Settings(database_url=fresh_database_url, direct_database_url="")

    # Act
    await create_schema(settings, fresh_engine)

    # Assert
    assert set(SQLModel.metadata.tables) <= await _table_names(fresh_engine)


# ========== Indexes ==========


async def test_a_fresh_database_gets_the_query_indexes_and_not_the_unused_ones(fresh_engine: AsyncEngine):
    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    indexes = await _index_names(fresh_engine)
    assert KEPT_INDEXES.issubset(indexes)
    assert indexes.isdisjoint(DROPPED_INDEXES)


async def test_a_server_booted_by_the_previous_code_loses_the_unused_indexes(fresh_engine: AsyncEngine):
    # Prepare
    await _create_tables_as_the_previous_code_did(fresh_engine)
    assert DROPPED_INDEXES.issubset(await _index_names(fresh_engine))

    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    indexes = await _index_names(fresh_engine)
    assert KEPT_INDEXES.issubset(indexes)
    assert indexes.isdisjoint(DROPPED_INDEXES)


async def test_two_usernames_differing_only_in_case_cannot_both_be_stored(fresh_engine: AsyncEngine):
    # Prepare
    await create_db_and_tables(fresh_engine)
    async with AsyncSession(fresh_engine) as session:
        session.add(_user("Ali", "ali.one@x.com"))
        await session.commit()

        # Act / Assert: the backstop behind username_claim_lock
        session.add(_user("ali", "ali.two@x.com"))
        with pytest.raises(IntegrityError, match="ix_user_username_lower"):
            await session.commit()
        await session.rollback()

    # Assert
    assert await _stored_users(fresh_engine) == [("Ali", "ali.one@x.com")]


async def test_two_emails_differing_only_in_case_cannot_both_be_stored(fresh_engine: AsyncEngine):
    # Prepare
    await create_db_and_tables(fresh_engine)
    async with AsyncSession(fresh_engine) as session:
        session.add(_user("ali_one", "Ali@x.com"))
        await session.commit()

        # Act / Assert: one account per mailbox, whatever the case (SEC-F14)
        session.add(_user("ali_two", "ali@x.com"))
        with pytest.raises(IntegrityError, match="ix_user_email_lower"):
            await session.commit()
        await session.rollback()

    # Assert
    assert await _stored_users(fresh_engine) == [("ali_one", "Ali@x.com")]


async def test_the_tables_added_by_this_release_are_created(fresh_engine: AsyncEngine):
    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    assert {"room_ban", "auth_session"} <= await _table_names(fresh_engine)


async def test_a_case_variant_duplicate_already_stored_is_logged_and_never_blocks_the_boot(
    fresh_engine: AsyncEngine,
):
    # Prepare: a server whose data the new unique indexes would refuse
    await _create_tables_as_the_previous_code_did(fresh_engine)
    async with AsyncSession(fresh_engine) as session:
        session.add_all([_user("Ali", "Ali@x.com"), _user("ali", "ali@x.com")])
        await session.commit()
    logged: list[str] = []
    sink_id = logger.add(logged.append, level="WARNING", format="{message}")

    # Act
    try:
        await create_db_and_tables(fresh_engine)
    finally:
        logger.remove(sink_id)

    # Assert: the two unique indexes are skipped and said so, the rest of the DDL ran
    indexes = await _index_names(fresh_engine)
    assert "ix_user_username_lower" not in indexes
    assert "ix_user_email_lower" not in indexes
    assert {"ix_chatmessage_user_id", "ix_userstats_total_games_won_desc"} <= indexes
    assert indexes.isdisjoint(DROPPED_INDEXES)
    assert any("ix_user_username_lower" in message for message in logged)
    assert any("ix_user_email_lower" in message for message in logged)
    assert await _stored_users(fresh_engine) == [("Ali", "Ali@x.com"), ("ali", "ali@x.com")]


async def test_a_table_held_by_a_long_transaction_never_stalls_the_boot(fresh_engine: AsyncEngine):
    # Prepare: a server booted by the previous code, and a transaction writing to `game`
    # that does not end (an old worker's request, a psql session left open)
    await _create_tables_as_the_previous_code_did(fresh_engine)
    logged: list[str] = []
    sink_id = logger.add(logged.append, level="WARNING", format="{message}")
    async with fresh_engine.connect() as holder:
        await holder.begin()
        await holder.execute(text("LOCK TABLE game IN ROW EXCLUSIVE MODE"))

        # Act: the old code's CREATE INDEX IF NOT EXISTS on game waited for this lock forever
        try:
            await asyncio.wait_for(create_db_and_tables(fresh_engine), timeout=BOOT_DEADLINE_SECONDS)
        finally:
            logger.remove(sink_id)
        await holder.rollback()

    # Assert: only the statement on the locked table is skipped, and said so
    indexes = await _index_names(fresh_engine)
    assert "ix_game_live_state_gin" in indexes
    assert "ix_roomuserlink_room_id" not in indexes
    assert KEPT_INDEXES.issubset(indexes)
    assert any("ix_game_live_state_gin" in message for message in logged)

    # Act: the next boot, with the table free again
    await create_db_and_tables(fresh_engine)

    # Assert
    assert (await _index_names(fresh_engine)).isdisjoint(DROPPED_INDEXES)
