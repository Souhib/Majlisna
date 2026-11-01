"""generate_fake_data.py must never drop or refill a production database by accident.

PD-02 / BDP-01 / INFRA-01: the documented schema-change procedure was ``--delete`` then
``--create-db``, run inside the production container, and nothing stopped it: the
drop erased every real account and the reseed put 31 fake ones, 16 of them with the
passwords this public repository prints, in their place. With no backup, for good.

In production, ``--delete`` and ``--create-db`` now exit with code 2 before anything
touches the database, unless the operator passes BOTH ``--i-know-this-is-production``
and ``--dump-taken <path>`` naming a pg_dump custom-format archive (magic ``PGDMP``)
written less than an hour ago. ``--seed``, the content upsert, stays allowed: it is the
only thing production should ever run.
"""

import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from majlisna.api.constants import PG_DUMP_CUSTOM_FORMAT_MAGIC, PRODUCTION_DUMP_MAX_AGE_SECONDS
from majlisna.settings import Settings
from scripts import generate_fake_data

# What `pg_dump -Fc` writes first: the magic, then the archive version bytes.
PG_DUMP_HEADER = PG_DUMP_CUSTOM_FORMAT_MAGIC + b"\x01\x0f\x00\x04\x08\x01\x01\x01"


def _settings(environment: str) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        direct_database_url="",
        jwt_secret_key="a-real-secret-for-the-production-guard-tests",
        environment=environment,
        log_level="WARNING",
        cors_origins="http://localhost:3000",
    )


def _write_dump(path: Path, *, content: bytes = PG_DUMP_HEADER, age_seconds: float = 0) -> Path:
    path.write_bytes(content + b"\x00" * 64)
    if age_seconds:
        instant = time.time() - age_seconds
        os.utime(path, (instant, instant))
    return path


@pytest.fixture(name="database")
def mocked_database(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Every way main() can reach a database, replaced by a mock that records the call."""
    engine = MagicMock(name="engine")
    engine.dispose = AsyncMock()
    calls = MagicMock(name="database")
    calls.engine = engine
    calls.create_app_engine = AsyncMock(return_value=engine)
    calls.create_db_and_tables = AsyncMock()
    calls.generate_all_data = AsyncMock()
    calls.seed_game_content = AsyncMock()
    monkeypatch.setattr(generate_fake_data, "create_app_engine", calls.create_app_engine)
    monkeypatch.setattr(generate_fake_data, "create_db_and_tables", calls.create_db_and_tables)
    monkeypatch.setattr(generate_fake_data, "generate_all_data", calls.generate_all_data)
    monkeypatch.setattr(generate_fake_data, "seed_game_content", calls.seed_game_content)
    return calls


@pytest.fixture(name="production")
def production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production container: MAJLISNA_ENV=production (docker-compose.dokploy.yml)."""
    monkeypatch.setenv("MAJLISNA_ENV", "production")
    monkeypatch.setattr(generate_fake_data, "Settings", lambda: _settings("production"))


@pytest.fixture(name="development")
def development_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The E2E stack and a developer's machine: MAJLISNA_ENV=development."""
    monkeypatch.setenv("MAJLISNA_ENV", "development")
    monkeypatch.setattr(generate_fake_data, "Settings", lambda: _settings("development"))


# ── Refused in production ────────────────────────────────────────────────────


@pytest.mark.usefixtures("production")
@pytest.mark.parametrize("destructive_flag", ["--delete", "-d", "--create-db", "-c"])
async def test_a_destructive_run_in_production_exits_2_before_touching_the_database(
    database: MagicMock, destructive_flag: str, capsys: pytest.CaptureFixture[str]
):
    # Prepare: the production container, no override

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main([destructive_flag])

    # Assert: refused, and nothing reached the database — not even an engine
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0
    assert database.create_app_engine.await_count == 0
    assert database.generate_all_data.await_count == 0
    message = capsys.readouterr().err
    assert "production" in message
    assert "--seed" in message


@pytest.mark.parametrize(
    ("majlisna_env", "environment"),
    [("production", "development"), ("", "production"), ("Production", "development")],
    ids=["MAJLISNA_ENV", "ENVIRONMENT", "MAJLISNA_ENV-any-case"],
)
async def test_either_production_marker_is_enough_to_refuse(
    database: MagicMock, monkeypatch: pytest.MonkeyPatch, majlisna_env: str, environment: str
):
    # Prepare: production named by MAJLISNA_ENV alone, or by ENVIRONMENT alone
    if majlisna_env:
        monkeypatch.setenv("MAJLISNA_ENV", majlisna_env)
    else:
        monkeypatch.delenv("MAJLISNA_ENV", raising=False)
    monkeypatch.setattr(generate_fake_data, "Settings", lambda: _settings(environment))

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--delete"])

    # Assert
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0


@pytest.mark.usefixtures("production")
async def test_the_confirmation_flag_alone_is_not_enough(database: MagicMock):
    # Prepare: no dump

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--delete", "--i-know-this-is-production"])

    # Assert
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0


@pytest.mark.usefixtures("production")
async def test_a_fresh_dump_alone_is_not_enough(database: MagicMock, tmp_path: Path):
    # Prepare
    dump = _write_dump(tmp_path / "majlisna.dump")

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--delete", "--dump-taken", str(dump)])

    # Assert
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0


@pytest.mark.usefixtures("production")
async def test_a_dump_older_than_an_hour_is_refused(
    database: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # Prepare: a real pg_dump archive, but from before the last hour's writes
    dump = _write_dump(tmp_path / "majlisna.dump", age_seconds=PRODUCTION_DUMP_MAX_AGE_SECONDS + 60)

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--delete", "--i-know-this-is-production", "--dump-taken", str(dump)])

    # Assert
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0
    assert "old" in capsys.readouterr().err


@pytest.mark.usefixtures("production")
@pytest.mark.parametrize(
    "content",
    [b"--\n-- PostgreSQL database dump\n--\n", b"", b"PGDM"],
    ids=["plain-sql-dump", "empty-file", "truncated-magic"],
)
async def test_a_file_that_is_not_a_pg_dump_archive_is_refused(
    database: MagicMock, tmp_path: Path, content: bytes, capsys: pytest.CaptureFixture[str]
):
    # Prepare: fresh, but not what `pg_dump -Fc` writes
    dump = tmp_path / "majlisna.dump"
    dump.write_bytes(content)

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--create-db", "--i-know-this-is-production", "--dump-taken", str(dump)])

    # Assert
    assert exit_info.value.code == 2
    assert database.generate_all_data.await_count == 0
    assert "PGDMP" in capsys.readouterr().err


@pytest.mark.usefixtures("production")
async def test_a_missing_dump_file_is_refused(database: MagicMock, tmp_path: Path):
    # Prepare
    missing = tmp_path / "never-taken.dump"

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--delete", "--i-know-this-is-production", "--dump-taken", str(missing)])

    # Assert
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0


@pytest.mark.usefixtures("production")
async def test_a_dump_dated_in_the_future_is_refused(database: MagicMock, tmp_path: Path):
    # Prepare: `touch -d tomorrow` must not make an old dump look fresh
    dump = _write_dump(tmp_path / "majlisna.dump", age_seconds=-PRODUCTION_DUMP_MAX_AGE_SECONDS)

    # Act
    with pytest.raises(SystemExit) as exit_info:
        await generate_fake_data.main(["--delete", "--i-know-this-is-production", "--dump-taken", str(dump)])

    # Assert
    assert exit_info.value.code == 2
    assert database.create_db_and_tables.await_count == 0


# ── Allowed ──────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("production")
async def test_seed_is_allowed_in_production_without_any_flag(database: MagicMock):
    # Prepare: the production container

    # Act
    await generate_fake_data.main(["--seed"])

    # Assert: the content upsert ran, and nothing was dropped
    assert database.seed_game_content.await_count == 1
    assert database.create_db_and_tables.await_count == 0
    assert database.engine.dispose.await_count == 1


@pytest.mark.usefixtures("production")
async def test_both_overrides_with_a_fresh_dump_let_the_drop_through(database: MagicMock, tmp_path: Path):
    # Prepare: the operator took a dump a minute ago and says so
    dump = _write_dump(tmp_path / "majlisna.dump", age_seconds=60)

    # Act
    await generate_fake_data.main(["--delete", "--i-know-this-is-production", "--dump-taken", str(dump)])

    # Assert
    database.create_db_and_tables.assert_awaited_once_with(database.engine, drop_all=True)


@pytest.mark.usefixtures("production")
async def test_both_overrides_with_a_fresh_dump_let_create_db_through(database: MagicMock, tmp_path: Path):
    # Prepare
    dump = _write_dump(tmp_path / "majlisna.dump")

    # Act
    await generate_fake_data.main(["--create-db", "--i-know-this-is-production", "--dump-taken", str(dump)])

    # Assert
    assert database.generate_all_data.await_count == 1


@pytest.mark.usefixtures("development")
@pytest.mark.parametrize("destructive_flag", ["--delete", "--create-db"])
async def test_development_needs_no_override(database: MagicMock, destructive_flag: str):
    """The E2E reseed (e2e/run-local.sh, global-setup.ts) runs --delete then --create-db, flagless."""
    # Prepare: MAJLISNA_ENV=development, no dump

    # Act
    await generate_fake_data.main([destructive_flag])

    # Assert
    if destructive_flag == "--delete":
        database.create_db_and_tables.assert_awaited_once_with(database.engine, drop_all=True)
    else:
        assert database.generate_all_data.await_count == 1
