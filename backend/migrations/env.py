"""Alembic's environment for Majlisna: PostgreSQL only, async (asyncpg). See backend/CLAUDE.md.

Two ways in:

- **The app, at boot** (``majlisna/schema.py``): it hands its connection in
  ``config.attributes["connection"]``, inside the transaction that already holds the
  schema lock. Everything runs on that connection, in that transaction; the app's loggers
  are left alone (no ``fileConfig``).
- **The CLI** (``uv run alembic ...`` from backend/): its own engine, on
  ``DIRECT_DATABASE_URL`` when set (it bypasses PgBouncer, like every DDL), else
  ``DATABASE_URL``, both read through ``majlisna.settings.Settings``. It takes the same
  schema lock as the boot, so a CLI upgrade never races a booting worker.

``target_metadata`` is ``SQLModel.metadata`` with every model registered (``majlisna.schema``
imports ``majlisna.api.models.table``, which imports them all). Types are compared
(``compare_type``); the PostgreSQL-only indexes the models do not declare are left out
(``schema.include_object``). Autogenerate does not see a new value of a native enum: write
the ``ALTER TYPE ... ADD VALUE`` by hand (tests/api/test_migrations.py fails otherwise).
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from majlisna.schema import CONNECTION_ATTRIBUTE, include_object, lock_schema
from majlisna.settings import Settings

config = context.config
target_metadata = SQLModel.metadata


def database_url() -> str:
    """The CLI's database: the direct URL when set, else DATABASE_URL. PostgreSQL only."""
    settings = Settings()
    url = settings.direct_database_url or settings.database_url
    if not url.startswith("postgresql"):
        message = (
            f"Migrations run on PostgreSQL only, and this URL is not one ({url.split(':', 1)[0]}). "
            "SQLite (dev, tests) builds its schema with create_all at boot. Point DATABASE_URL at a "
            "PostgreSQL 16, e.g. a throwaway `docker run -d -p 127.0.0.1:55432:5432 -e "
            "POSTGRES_PASSWORD=postgres postgres:16-alpine` and "
            "DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/postgres"
        )
        raise SystemExit(message)
    return url


def run_migrations_offline() -> None:
    """``alembic upgrade --sql``: the SQL of the migrations, printed, no database."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    """Run the command on ``connection``: in the app's transaction, or in one of its own."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        lock_schema(connection)
        context.run_migrations()


async def run_migrations_from_the_cli() -> None:
    engine = create_async_engine(database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


app_connection = config.attributes.get(CONNECTION_ATTRIBUTE)
if app_connection is not None:
    run_migrations(app_connection)
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_from_the_cli())
