"""WP-19 (TQ-11, INFRA-16): what the shared fixtures of ``tests/conftest.py`` promise.

- **Fixture passwords are hashed at bcrypt's cheapest cost.** Production hashes at
  ``gensalt()``'s default, 12: 0.24 s a hash, so a five-player game test spent 1.2 s of
  its 3.6 s in ``create_user``, and about two thirds of the suite's CPU went to hashing
  test passwords (TQ-11). The autouse ``cheap_bcrypt`` fixture swaps
  ``majlisna.api.controllers.shared.gensalt`` for cost 4; a test marked ``real_bcrypt``
  keeps the production cost.
- **A test that does not ask for the database gets none.** ``clear_database`` was
  autouse and depended on the engine, so even a pure-function test built (on SQLite) or
  re-checked (on PostgreSQL) the whole schema and truncated 33 tables one by one: 51
  database-free tests took 41 s with ``--use-postgres`` against 13 s on SQLite (INFRA-16).
- **On PostgreSQL the schema is the session's**, created once, and every test that used
  it is followed by ONE ``TRUNCATE … RESTART IDENTITY CASCADE`` of every table: the next
  test starts with empty tables (``room_ban`` and ``auth_session`` included) and fresh
  sequences.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.shared import async_get_password_hash, get_password_hash, verify_password
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room_ban import RoomBan

# bcrypt's lowest cost, as the "$2b$<cost>$" prefix of a hash.
CHEAP_HASH_PREFIX = "$2b$04$"
# gensalt()'s default: what production stores.
PRODUCTION_HASH_PREFIX = "$2b$12$"
# The fixtures that stand for "this test uses the database".
DATABASE_FIXTURES = ("engine", "session", "postgres_schema", "postgres_container")


async def _row_counts(session: AsyncSession) -> dict[str, int]:
    """Rows in every table the models declare."""
    counts = {}
    for table in SQLModel.metadata.sorted_tables:
        counts[table.name] = (await session.exec(select(func.count()).select_from(table))).one()[0]
    return counts


# ========== bcrypt ==========


async def test_fixture_users_are_hashed_at_the_cheapest_cost(create_user):
    # Act
    user = await create_user(username="cheap", email="cheap@test.com", password="password123")

    # Assert: cheap, and still a real bcrypt hash of that password
    assert user.password.startswith(CHEAP_HASH_PREFIX)
    assert verify_password("password123", user.password)
    assert not verify_password("password124", user.password)


async def test_the_hash_of_a_registration_is_cheap_too():
    # Act: the path register, password change and reset take (a thread of the pool)
    hashed = await async_get_password_hash("password123")

    # Assert
    assert hashed.startswith(CHEAP_HASH_PREFIX)
    assert verify_password("password123", hashed)


@pytest.mark.real_bcrypt
def test_the_real_bcrypt_marker_keeps_the_production_cost():
    # Act
    hashed = get_password_hash("password123")

    # Assert
    assert hashed.startswith(PRODUCTION_HASH_PREFIX)
    assert verify_password("password123", hashed)


# ========== No database for a test that does not use one ==========


def test_a_test_without_the_database_sets_none_up(request: pytest.FixtureRequest):
    # Assert: no engine, no schema, no cleanup, and on PostgreSQL no container start
    assert [name for name in DATABASE_FIXTURES if name in request.fixturenames] == []


async def test_a_test_with_the_database_has_its_schema(session: AsyncSession):
    # Act / Assert: every table the models declare can be read
    assert set(await _row_counts(session)) == set(SQLModel.metadata.tables)


# ========== One schema per session, emptied after each test ==========


@pytest.mark.postgres
async def test_every_test_on_postgres_gets_the_sessions_schema(engine, postgres_schema):
    # Assert: the engine is the session's, not one built (and its schema re-checked) per test
    assert engine is postgres_schema.engine


@pytest.mark.parametrize("run", ["first", "second"])
async def test_every_test_starts_with_empty_tables_and_fresh_sequences(
    session: AsyncSession, create_user, create_room, run: str
):
    # Assert: the previous test (the other run of this one, or any other) left nothing behind
    assert {name: count for name, count in (await _row_counts(session)).items() if count} == {}

    # Act: write rows in the tables the wave-1 tests added, and in the one serial key
    host = await create_user(username=f"host_{run}", email=f"host_{run}@test.com")
    guest = await create_user(username=f"guest_{run}", email=f"guest_{run}@test.com")
    room = await create_room(owner=host)
    session.add(RoomBan(room_id=room.id, user_id=guest.id, banned_by=host.id))
    session.add(
        AuthSession(user_id=host.id, expires_at=datetime.now(UTC) + timedelta(days=1), current_refresh_jti=f"jti-{run}")
    )
    await session.commit()

    # Assert: the owner's seat is the first row of roomuserlink, whatever ran before
    link = (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room.id))).one()[0]
    assert link.id == 1
    counts = await _row_counts(session)
    assert counts["room_ban"] == 1
    assert counts["auth_session"] == 1
