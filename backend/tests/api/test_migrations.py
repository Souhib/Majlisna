"""The schema on PostgreSQL is the Alembic migrations' (backend/CLAUDE.md, "Migrations (Alembic)").

What these tests hold, each against databases of its own in the session's container (the
unique ``lower()`` indexes must never reach the shared test database, where other tests
store case variants on purpose):

- **the baseline is production**: it builds, catalog line for catalog line, the schema
  production had on 2026-11-01 (``tests/fixtures/production_schema_2026-11-01.sql``, a
  ``pg_dump --schema-only`` of it, no data);
- **the migrations are the models** (the drift guard, ``alembic check``): a database at head
  is what the models declare, enum values included, and a model changed without a
  migration fails the check;
- **the boot**: every worker runs it, one at a time (INFRA-13), over the direct URL; a
  database created before migrations is adopted once, its data untouched, and refused,
  untouched, when its schema is not the baseline's;
- the seed script's ``--delete``, the lock timeout, and the CLI (test_migrations_offline.py:
  SQLite's ``create_all``, the CLI's refusal of SQLite, the models' registration).
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    ALEMBIC_BASELINE_REVISION,
    ALEMBIC_VERSION_TABLE,
    POSTGRES_ONLY_INDEXES,
    SCHEMA_ADOPTION_PROBE_SCHEMA,
)
from majlisna.api.models.table import User
from majlisna.database import create_db_and_tables, create_schema
from majlisna.schema import (
    BACKEND_DIR,
    SchemaAdoptionRefusedError,
    alembic_config,
    describe_schema,
    include_object,
)
from majlisna.settings import Settings

# UVICORN_WORKERS in backend/Dockerfile.
CONCURRENT_BOOTS = 4

# One uvicorn worker's startup, in a process of its own as in production: Alembic's
# `context` and `op` are process-global, so four boots interleaved in one event loop are
# not what four workers do (and, without the schema lock, they deadlock the loop instead
# of failing). The worker exits 0 once its schema is at head.
WORKER_BOOT = """
import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from majlisna.database import create_schema
from majlisna.settings import Settings


async def boot(direct_url, unreachable_url):
    settings = Settings(database_url=unreachable_url, direct_database_url=direct_url)
    app_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        await create_schema(settings, app_engine)
    finally:
        await app_engine.dispose()


asyncio.run(boot(sys.argv[1], sys.argv[2]))
"""

# Far above SCHEMA_DDL_LOCK_TIMEOUT (5 s): a boot that takes longer behind a held table
# lock is a boot that would have waited for it forever.
BOOT_DEADLINE_SECONDS = 30

# Nothing listens on the discard port: an engine on this URL fails at its first connect.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://nobody:nothing@127.0.0.1:9/unreachable"

PRODUCTION_SCHEMA_SNAPSHOT = Path(__file__).resolve().parent.parent / "fixtures" / "production_schema_2026-11-01.sql"
PRODUCTION_TABLE_COUNT = 33

# What the old startup DDL left on servers booted before WP-21; production has neither.
LEGACY_INDEXES = {"ix_game_live_state_gin", "ix_roomuserlink_room_id"}

# Two seeded accounts written in SQL against the baseline's columns, never through the
# models: the models will move on, production's schema of 2026-11-01 will not.
SEED_USERS_SQL = """
INSERT INTO "user" (id, username, email_address, email_verified, auth_provider, password)
VALUES ('6f1d6e2a-0000-4000-8000-000000000001', 'Amina', 'amina@example.org', true, 'email', 'x'),
       ('6f1d6e2a-0000-4000-8000-000000000002', 'yusuf', 'yusuf@example.org', false, 'google', 'y')
"""
SEEDED_USERS = [("Amina", "amina@example.org"), ("yusuf", "yusuf@example.org")]

pytestmark = pytest.mark.postgres


# ========== Helpers ==========


class ThrowawayDatabases:
    """Empty databases in the session's container, all dropped at the end of the test."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._admin = create_async_engine(base_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        self._names: list[str] = []
        self._engines: list[AsyncEngine] = []

    async def create(self) -> str:
        name = f"migrations_{uuid4().hex}"
        async with self._admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
        self._names.append(name)
        return f"{self.base_url.rsplit('/', 1)[0]}/{name}"

    def engine(self, url: str) -> AsyncEngine:
        """An engine on ``url`` the way a worker's would be (no shared pool), disposed at the end."""
        engine = create_async_engine(url, poolclass=NullPool)
        self._engines.append(engine)
        return engine

    async def close(self) -> None:
        for engine in self._engines:
            await engine.dispose()
        async with self._admin.connect() as conn:
            for name in self._names:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await self._admin.dispose()


@pytest_asyncio.fixture(name="databases")
async def get_databases(postgres_container) -> AsyncIterator[ThrowawayDatabases]:
    base_url = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    databases = ThrowawayDatabases(base_url)
    yield databases
    await databases.close()


@pytest_asyncio.fixture(name="fresh_url")
async def get_fresh_url(databases: ThrowawayDatabases) -> str:
    return await databases.create()


@pytest_asyncio.fixture(name="fresh_engine")
async def get_fresh_engine(databases: ThrowawayDatabases, fresh_url: str) -> AsyncEngine:
    return databases.engine(fresh_url)


@pytest_asyncio.fixture(name="production_url")
async def get_production_url(databases: ThrowawayDatabases) -> str:
    """A database restored from production's schema of 2026-11-01: created before migrations."""
    url = await databases.create()
    await _execute_script(url, _production_schema_sql())
    return url


@pytest_asyncio.fixture(name="production_engine")
async def get_production_engine(databases: ThrowawayDatabases, production_url: str) -> AsyncEngine:
    return databases.engine(production_url)


def _production_schema_sql() -> str:
    """The snapshot without psql's meta-commands (``\\restrict``), which no server runs."""
    lines = PRODUCTION_SCHEMA_SNAPSHOT.read_text().splitlines()
    return "\n".join(line for line in lines if not line.startswith("\\"))


async def _execute_script(url: str, script: str) -> None:
    """Run a multi-statement SQL script, as psql would (asyncpg's simple query protocol)."""
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await connection.execute(script)
    finally:
        await connection.close()


async def _boot(url: str) -> None:
    """One worker's startup: its own engine, then the schema (main.py's lifespan)."""
    settings = Settings(database_url=UNREACHABLE_DATABASE_URL, direct_database_url=url)
    app_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        await create_schema(settings, app_engine)
    finally:
        await app_engine.dispose()


async def _boot_workers(url: str) -> list[tuple[int | None, str]]:
    """Boot CONCURRENT_BOOTS worker processes on ``url`` at once: each one's exit code and log."""
    processes = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            WORKER_BOOT,
            url,
            UNREACHABLE_DATABASE_URL,
            cwd=BACKEND_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        for _ in range(CONCURRENT_BOOTS)
    ]
    try:
        outputs = await asyncio.wait_for(
            asyncio.gather(*(process.communicate() for process in processes)), timeout=BOOT_DEADLINE_SECONDS
        )
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
    return [(process.returncode, stderr.decode()) for process, (_, stderr) in zip(processes, outputs, strict=True)]


async def _describe(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(describe_schema)


async def _versions(engine: AsyncEngine) -> list[str] | None:
    """The rows of alembic_version, or None when the table does not exist."""
    async with engine.connect() as conn:
        exists = (await conn.execute(text("SELECT to_regclass(:name)"), {"name": ALEMBIC_VERSION_TABLE})).scalar()
        if exists is None:
            return None
        return list((await conn.execute(text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}"))).scalars())


async def _schema_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return set((await conn.execute(text("SELECT nspname FROM pg_namespace"))).scalars())


async def _index_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        return set(rows.scalars())


async def _stored_users(engine: AsyncEngine) -> list[tuple[str, str]]:
    async with engine.connect() as conn:
        rows = await conn.execute(text('SELECT username, email_address FROM "user" ORDER BY username'))
        return [(row[0], row[1]) for row in rows]


def _head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def _run_alembic(connection: Connection, action: str, revision: str) -> None:
    config = alembic_config(connection)
    if action == "upgrade":
        command.upgrade(config, revision)
    else:
        command.downgrade(config, revision)


async def _alembic(engine: AsyncEngine, action: str, revision: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_run_alembic, action, revision)


def _model_differences(connection: Connection, metadata: sa.MetaData) -> list:
    """What `alembic check` compares: the database against ``metadata``, as env.py configures it."""
    context = MigrationContext.configure(connection, opts={"compare_type": True, "include_object": include_object})
    return compare_metadata(context, metadata)


def _enum_differences(connection: Connection, metadata: sa.MetaData) -> list[str]:
    """Native enum types whose labels differ from what ``metadata`` declares (autogenerate ignores these)."""
    declared = {
        column.type.name: list(column.type.enums)
        for table in metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, sa.Enum) and column.type.native_enum and column.type.name
    }
    rows = connection.execute(
        text(
            "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = current_schema() GROUP BY t.typname"
        )
    )
    stored = {name: list(labels) for name, labels in rows}
    return [
        f"{name}: models {labels}, database {stored.get(name)}"
        for name, labels in sorted(declared.items())
        if stored.get(name) != labels
    ]


def _copy_of_the_models() -> sa.MetaData:
    copy = sa.MetaData()
    for table in SQLModel.metadata.tables.values():
        table.to_metadata(copy)
    return copy


def _operation_kinds(differences: list) -> set[str]:
    """The kind of each autogenerate difference (a column's are grouped in a list)."""
    kinds: set[str] = set()
    for difference in differences:
        kinds.update(item[0] for item in (difference if isinstance(difference, list) else [difference]))
    return kinds


def _user(username: str, email_address: str) -> User:
    return User(username=username, email_address=email_address, password="not-a-real-hash")


# ========== The baseline is production ==========


async def test_the_baseline_builds_exactly_the_production_schema(
    fresh_engine: AsyncEngine, production_engine: AsyncEngine
):
    # Act
    await _alembic(fresh_engine, "upgrade", ALEMBIC_BASELINE_REVISION)

    # Assert: every table, column (in its order), default, constraint, index, enum, sequence
    baseline = await _describe(fresh_engine)
    production = await _describe(production_engine)
    assert baseline == production
    assert len([line for line in baseline if line.startswith("table ")]) == PRODUCTION_TABLE_COUNT
    assert any("fk_room_active_game_id" in line for line in baseline)
    assert POSTGRES_ONLY_INDEXES.issubset(await _index_names(fresh_engine))


async def test_the_baseline_downgrades_to_an_empty_schema_and_builds_again(fresh_engine: AsyncEngine):
    # Prepare
    await _alembic(fresh_engine, "upgrade", ALEMBIC_BASELINE_REVISION)
    built = await _describe(fresh_engine)

    # Act
    await _alembic(fresh_engine, "downgrade", "base")
    emptied = await _describe(fresh_engine)
    await _alembic(fresh_engine, "upgrade", ALEMBIC_BASELINE_REVISION)

    # Assert: no table, no enum type left behind (drop_table keeps them)
    assert emptied == []
    assert await _describe(fresh_engine) == built


# ========== The migrations are the models (the drift guard) ==========


async def test_a_database_at_head_is_what_the_models_declare(fresh_engine: AsyncEngine):
    # Prepare
    await create_db_and_tables(fresh_engine)

    # Act
    async with fresh_engine.connect() as conn:
        differences = await conn.run_sync(_model_differences, SQLModel.metadata)
        enum_differences = await conn.run_sync(_enum_differences, SQLModel.metadata)

    # Assert: `alembic check` would find nothing to write, and every enum value is there
    assert differences == []
    assert enum_differences == []


async def test_a_model_changed_without_a_migration_fails_the_drift_check(fresh_engine: AsyncEngine):
    # Prepare: the models, plus a column, a table, a longer string and an enum value
    await create_db_and_tables(fresh_engine)
    changed = _copy_of_the_models()
    changed.tables["user"].append_column(sa.Column("nickname", sa.String(), nullable=True))
    sa.Table("tournament", changed, sa.Column("id", sa.Integer(), primary_key=True))
    changed.tables["user"].c.bio.type = sa.String(length=500)
    game_type = changed.tables["game"].c.type
    game_type.type = sa.Enum(*game_type.type.enums, "CHESS", name="gametype")

    # Act
    async with fresh_engine.connect() as conn:
        differences = await conn.run_sync(_model_differences, changed)
        enum_differences = await conn.run_sync(_enum_differences, changed)

    # Assert
    assert {"add_column", "add_table", "modify_type"} <= _operation_kinds(differences)
    assert len(enum_differences) == 1
    assert "CHESS" in enum_differences[0]


async def test_the_cli_upgrades_and_checks_a_fresh_database(fresh_url: str):
    # Prepare: what CI's backend job runs, through migrations/env.py's own engine
    environment = {**os.environ, "DATABASE_URL": fresh_url, "DIRECT_DATABASE_URL": ""}

    # Act
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    check = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert upgrade.returncode == 0, upgrade.stderr
    assert check.returncode == 0, check.stderr
    assert "No new upgrade operations detected" in check.stdout + check.stderr


# ========== Boot: a fresh database ==========


async def test_a_fresh_database_is_migrated_to_head(fresh_engine: AsyncEngine):
    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    assert await _versions(fresh_engine) == [_head_revision()]
    tables = [line.removeprefix("table ") for line in await _describe(fresh_engine) if line.startswith("table ")]
    assert set(tables) == set(SQLModel.metadata.tables)


async def test_four_workers_booting_on_a_fresh_database_all_succeed(fresh_url: str, fresh_engine: AsyncEngine):
    # Act
    workers = await _boot_workers(fresh_url)

    # Assert: one migrated, the others found the database at head
    assert [log for code, log in workers if code != 0] == []
    assert len([log for _, log in workers if "Schema: migrated" in log]) == 1
    assert await _versions(fresh_engine) == [_head_revision()]


async def test_a_second_boot_changes_nothing(fresh_engine: AsyncEngine):
    # Prepare
    await create_db_and_tables(fresh_engine)
    after_first_boot = await _describe(fresh_engine)

    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    assert await _describe(fresh_engine) == after_first_boot
    assert await _versions(fresh_engine) == [_head_revision()]


async def test_the_app_migrates_over_the_direct_connection(fresh_url: str, fresh_engine: AsyncEngine):
    # Prepare: DATABASE_URL (PgBouncer in production) cannot be reached, the direct URL can

    # Act
    await _boot(fresh_url)

    # Assert
    assert await _versions(fresh_engine) == [_head_revision()]


async def test_without_a_direct_url_the_app_engine_migrates(fresh_url: str, fresh_engine: AsyncEngine):
    # Prepare
    settings = Settings(database_url=fresh_url, direct_database_url="")

    # Act
    await create_schema(settings, fresh_engine)

    # Assert
    assert await _versions(fresh_engine) == [_head_revision()]


async def test_a_fresh_database_gets_the_postgres_only_indexes_and_not_the_legacy_ones(fresh_engine: AsyncEngine):
    # Act
    await create_db_and_tables(fresh_engine)

    # Assert
    indexes = await _index_names(fresh_engine)
    assert POSTGRES_ONLY_INDEXES.issubset(indexes)
    assert {"ix_chatmessage_user_id", "ix_userstats_user_id"} <= indexes
    assert indexes.isdisjoint(LEGACY_INDEXES)


@pytest.mark.parametrize(
    ("first", "second", "index"),
    [
        (("Ali", "ali.one@x.com"), ("ali", "ali.two@x.com"), "ix_user_username_lower"),
        (("ali_one", "Ali@x.com"), ("ali_two", "ali@x.com"), "ix_user_email_lower"),
    ],
)
async def test_a_case_variant_of_a_stored_username_or_address_is_refused(
    fresh_engine: AsyncEngine, first: tuple[str, str], second: tuple[str, str], index: str
):
    # Prepare
    await create_db_and_tables(fresh_engine)
    async with AsyncSession(fresh_engine) as session:
        session.add(_user(*first))
        await session.commit()

        # Act / Assert: the backstop behind username_claim_lock, one account per mailbox
        session.add(_user(*second))
        with pytest.raises(IntegrityError, match=index):
            await session.commit()
        await session.rollback()

    # Assert
    async with AsyncSession(fresh_engine) as session:
        rows = (await session.exec(select(User.username, User.email_address).order_by(col(User.username)))).all()
    assert [(row[0], row[1]) for row in rows] == [first]


# ========== Boot: a database created before migrations ==========


async def test_a_database_created_before_migrations_is_adopted_with_its_data(
    production_url: str, production_engine: AsyncEngine, fresh_engine: AsyncEngine
):
    # Prepare: production as it was, with accounts in it
    await _execute_script(production_url, SEED_USERS_SQL)
    assert await _versions(production_engine) is None

    # Act
    await _boot(production_url)

    # Assert: stamped at the baseline, then at head; the schema of a fresh one; data untouched
    await create_db_and_tables(fresh_engine)
    assert await _versions(production_engine) == [_head_revision()]
    assert await _describe(production_engine) == await _describe(fresh_engine)
    assert await _stored_users(production_engine) == SEEDED_USERS
    assert SCHEMA_ADOPTION_PROBE_SCHEMA not in await _schema_names(production_engine)


async def test_four_workers_booting_on_a_database_created_before_migrations_adopt_it_once(
    production_url: str, production_engine: AsyncEngine
):
    # Act
    workers = await _boot_workers(production_url)

    # Assert: one adopted it, the others found it at head
    assert [log for code, log in workers if code != 0] == []
    assert len([log for _, log in workers if "Schema: adopted" in log]) == 1
    assert await _versions(production_engine) == [_head_revision()]


async def test_an_extension_in_the_schema_does_not_stop_the_adoption(
    production_url: str, production_engine: AsyncEngine
):
    # Prepare: production preloads pg_stat_statements; its objects may be created by hand
    await _execute_script(production_url, "CREATE EXTENSION pg_stat_statements")

    # Act
    await _boot(production_url)

    # Assert
    assert await _versions(production_engine) == [_head_revision()]


@pytest.mark.parametrize(
    ("change", "kind", "named"),
    [
        # what the old optional startup DDL could leave behind (a case-variant duplicate)
        ("DROP INDEX ix_user_email_lower", "missing", "ix_user_email_lower"),
        # what a server booted before WP-21 still carries
        ("CREATE INDEX ix_game_live_state_gin ON game USING GIN (live_state)", "unexpected", "ix_game_live_state_gin"),
        ('ALTER TABLE "user" ADD COLUMN nickname varchar', "unexpected", "nickname"),
        ("DROP TABLE room_ban", "missing", "table room_ban"),
        ("ALTER TABLE room ALTER COLUMN password TYPE varchar(8)", "unexpected", "password character varying(8)"),
        ("ALTER TYPE gametype ADD VALUE 'CHESS'", "unexpected", "'CHESS'"),
    ],
    ids=["index-missing", "legacy-index", "column-added", "table-missing", "type-changed", "enum-value-added"],
)
async def test_a_database_whose_schema_is_not_the_baselines_is_refused_untouched(
    production_url: str, production_engine: AsyncEngine, change: str, kind: str, named: str
):
    # Prepare: production, changed by hand, with accounts in it
    await _execute_script(production_url, change)
    await _execute_script(production_url, SEED_USERS_SQL)
    before = await _describe(production_engine)

    # Act
    with pytest.raises(SchemaAdoptionRefusedError) as refusal:
        await _boot(production_url)

    # Assert: the difference is named, and nothing was written (no stamp, no probe left)
    differences = refusal.value.missing if kind == "missing" else refusal.value.unexpected
    assert any(named in line for line in differences), differences
    assert await _versions(production_engine) is None
    assert await _describe(production_engine) == before
    assert await _stored_users(production_engine) == SEEDED_USERS
    assert SCHEMA_ADOPTION_PROBE_SCHEMA not in await _schema_names(production_engine)


# ========== --delete, the lock timeout ==========


async def test_drop_all_empties_the_database_and_builds_it_at_head(fresh_engine: AsyncEngine):
    # Prepare: scripts/generate_fake_data.py --delete, on a database in use
    await create_db_and_tables(fresh_engine)
    built = await _describe(fresh_engine)
    async with AsyncSession(fresh_engine) as session:
        session.add(_user("amina", "amina@example.org"))
        await session.commit()

    # Act
    await create_db_and_tables(fresh_engine, drop_all=True)

    # Assert
    assert await _stored_users(fresh_engine) == []
    assert await _versions(fresh_engine) == [_head_revision()]
    assert await _describe(fresh_engine) == built


async def test_a_ddl_statement_behind_a_held_table_fails_fast_instead_of_stalling(fresh_engine: AsyncEngine):
    # Prepare: a transaction writing to `game` that does not end (a psql session left open)
    await create_db_and_tables(fresh_engine)
    async with fresh_engine.connect() as holder:
        await holder.begin()
        await holder.execute(text("LOCK TABLE game IN ROW EXCLUSIVE MODE"))

        # Act / Assert: the drop of `game` waits SCHEMA_DDL_LOCK_TIMEOUT, then the whole
        # transaction rolls back
        with pytest.raises(DBAPIError, match="lock timeout"):
            await asyncio.wait_for(create_db_and_tables(fresh_engine, drop_all=True), timeout=BOOT_DEADLINE_SECONDS)
        await holder.rollback()

    # Assert: nothing was dropped
    assert await _versions(fresh_engine) == [_head_revision()]
