"""The parts of the schema's setup that run without PostgreSQL (see test_migrations.py for the rest).

- SQLite (dev, the default test run) keeps ``create_all``: no migrations, no version table.
- The ``alembic`` CLI refuses any database but PostgreSQL, saying how to get one.
- ``models/table.py`` registers every model: ``migrations/env.py`` sees nothing else, so a
  model missing there would be invisible to autogenerate and to ``alembic check``.
"""

import os
import subprocess
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from majlisna.database import create_db_and_tables
from majlisna.schema import BACKEND_DIR

# A fresh interpreter: importing table.py alone must register every model of the package.
REGISTRATION_PROBE = """
import importlib
import pkgutil

import majlisna.api.models as models
import majlisna.api.models.table
from sqlmodel import SQLModel

registered = set(SQLModel.metadata.tables)
for module in pkgutil.iter_modules(models.__path__):
    importlib.import_module(f"majlisna.api.models.{module.name}")
print(sorted(set(SQLModel.metadata.tables) - registered))
"""


def _table_names(connection: Connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


@pytest.mark.parametrize("drop_all", [False, True])
async def test_sqlite_keeps_create_all_and_has_no_migrations(drop_all: bool):
    # Prepare
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    # Act
    try:
        await create_db_and_tables(engine, drop_all=drop_all)
        async with engine.connect() as conn:
            tables = await conn.run_sync(_table_names)
    finally:
        await engine.dispose()

    # Assert: every model's table, and no alembic_version
    assert tables == set(SQLModel.metadata.tables)


def test_the_cli_refuses_a_database_that_is_not_postgresql():
    # Prepare
    environment = {**os.environ, "DATABASE_URL": "sqlite+aiosqlite:///:memory:", "DIRECT_DATABASE_URL": ""}

    # Act
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode != 0
    assert "Migrations run on PostgreSQL only" in result.stderr


def test_table_py_registers_every_model_of_the_package():
    # Act
    result = subprocess.run(
        [sys.executable, "-c", REGISTRATION_PROBE],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )

    # Assert: nothing the package declares is missing from what env.py sees
    assert result.stdout.strip() == "[]"
