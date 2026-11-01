"""Tests for the game_lock module."""

import asyncio
import statistics
import time
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from asyncpg.exceptions import DeadlockDetectedError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers import game_lock
from majlisna.api.controllers.game_lock import _fallback_locks, _game_id_to_lock_key, cleanup_game_lock, get_game_lock

# Simultaneous moves on one table: 12 votes, 12 answers, the timer-expired burst.
CONTENDERS = 12
# How long each of them holds the lock — a small critical section.
HOLD_SECONDS = 0.005
# A queue served in order waits about CONTENDERS / 2 critical sections at the median
# (~50 ms here); the old 100 ms polling try-lock waited ~530 ms (BDP-06).
MEDIAN_WAIT_BUDGET_SECONDS = 0.150
# Bursts measured; the lowest median is the lock's own cost (machine load only adds to it).
BURSTS = 3
# Waiters queued one after the other in the arrival-order test.
QUEUED_WAITERS = 5
# How long the test gives one waiter to show up in pg_locks as waiting.
QUEUE_DEADLINE_SECONDS = 2.0

# ========== Fallback (asyncio.Lock) Tests ==========
#
# `_fallback_locks` is a WeakValueDictionary: an entry exists exactly while some task
# holds or awaits the lock, and is collected once the last reference goes. So these
# tests assert from INSIDE the `async with`, never after it — "the entry is gone
# afterwards" is the point of the weak map, not a regression.


async def test_creates_lock_on_use():
    """get_game_lock creates an asyncio.Lock when no session is provided."""
    async with get_game_lock("game-1"):
        assert isinstance(_fallback_locks["game-1"], asyncio.Lock)
        assert _fallback_locks["game-1"].locked()


async def test_returns_same_lock_for_same_id():
    """Concurrent holders of the same game_id share one lock, so they serialize."""
    order: list[str] = []

    async def hold(tag: str, delay: float) -> None:
        async with get_game_lock("game-shared"):
            order.append(f"{tag}-enter")
            await asyncio.sleep(delay)
            order.append(f"{tag}-exit")

    await asyncio.gather(hold("a", 0.05), hold("b", 0))

    # Interleaved entries would mean two different locks.
    assert order in (
        ["a-enter", "a-exit", "b-enter", "b-exit"],
        ["b-enter", "b-exit", "a-enter", "a-exit"],
    )


async def test_returns_different_locks_for_different_ids():
    """Different game_ids get independent locks and do not block each other."""
    async with get_game_lock("game-a"), get_game_lock("game-b"):
        assert _fallback_locks["game-a"] is not _fallback_locks["game-b"]


async def test_fallback_when_session_is_none():
    """Passing session=None uses fallback asyncio.Lock."""
    async with get_game_lock("game-1", session=None):
        assert "game-1" in _fallback_locks


async def test_unused_lock_is_not_retained():
    """An entry disappears once nothing holds the lock.

    This is what keeps `_fallback_locks` from growing one entry per game forever —
    `cleanup_game_lock` existed for that and had no caller anywhere in the app.
    """
    async with get_game_lock("game-transient"):
        assert "game-transient" in _fallback_locks
    assert "game-transient" not in _fallback_locks


async def test_cleanup_removes_existing_lock():
    """cleanup_game_lock drops a lock that is still referenced."""
    async with get_game_lock("game-1"):
        assert "game-1" in _fallback_locks
        cleanup_game_lock("game-1")
        assert "game-1" not in _fallback_locks


def test_cleanup_nonexistent_no_error():
    """cleanup_game_lock does not raise when the game_id doesn't exist."""
    cleanup_game_lock("nonexistent-id")


# ========== _game_id_to_lock_key Tests ==========


def test_game_id_to_lock_key_deterministic():
    """Same game_id always produces the same lock key."""
    key1 = _game_id_to_lock_key("abc-123")
    key2 = _game_id_to_lock_key("abc-123")
    assert key1 == key2


def test_game_id_to_lock_key_different_ids():
    """Different game_ids produce different lock keys."""
    key1 = _game_id_to_lock_key("game-a")
    key2 = _game_id_to_lock_key("game-b")
    assert key1 != key2


def test_game_id_to_lock_key_returns_int():
    """Lock key is an integer (required by pg_advisory_lock)."""
    key = _game_id_to_lock_key("some-uuid-string")
    assert isinstance(key, int)


def test_game_id_to_lock_key_fits_32_bits():
    """Lock key fits within 32 bits (positive)."""
    key = _game_id_to_lock_key("any-game-id")
    assert 0 <= key < 2**32


# ========== PostgreSQL Advisory Lock Tests ==========


@pytest.mark.postgres
async def test_pg_advisory_lock_acquires_and_releases(session: AsyncSession):
    """PostgreSQL advisory lock is acquired and released without error."""
    async with get_game_lock("pg-test-game", session=session):
        # Lock is held here — verify we're inside the lock
        pass
    # If we get here, lock was acquired and released successfully


@pytest.mark.postgres
async def test_pg_advisory_lock_no_fallback(session: AsyncSession):
    """With PostgreSQL, no fallback lock is created in _fallback_locks."""
    _fallback_locks.clear()
    async with get_game_lock("pg-no-fallback", session=session):
        pass
    assert "pg-no-fallback" not in _fallback_locks


@pytest.mark.postgres
async def test_pg_advisory_lock_reentrant_different_ids(session: AsyncSession):
    """Different game IDs can be locked sequentially on the same session."""
    async with get_game_lock("pg-game-1", session=session):
        pass
    async with get_game_lock("pg-game-2", session=session):
        pass


# ========== PostgreSQL: pooled connections, the wait queue, the timeout ==========
#
# The shared `engine` fixture uses NullPool on PostgreSQL: every session end CLOSES its
# connection, and a closed connection releases every lock it held, session-level ones
# included. So a session-level lock (`pg_advisory_lock`, which CLAUDE.md forbids)
# passed all 129 lock-related tests (TQ-06). Production pools its connections
# (AsyncAdaptedQueuePool, behind PgBouncer), so these tests build pooled engines.


def _asyncpg_url(postgres_container) -> str:
    return postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")


def _pooled_engine(postgres_container, pool_size: int) -> AsyncEngine:
    return create_async_engine(
        _asyncpg_url(postgres_container), poolclass=AsyncAdaptedQueuePool, pool_size=pool_size, max_overflow=0
    )


@pytest_asyncio.fixture(name="pooled_pair")
async def get_pooled_pair(postgres_container) -> AsyncGenerator[tuple[AsyncEngine, AsyncEngine]]:
    """Two pools of ONE connection each: a connection given back stays open in its pool."""
    engines = (_pooled_engine(postgres_container, 1), _pooled_engine(postgres_container, 1))
    yield engines
    for engine in engines:
        await engine.dispose()


@pytest_asyncio.fixture(name="pooled_engine")
async def get_pooled_engine(postgres_container) -> AsyncGenerator[AsyncEngine]:
    """One pool with a connection for every contender, plus one for the probe."""
    engine = _pooled_engine(postgres_container, CONTENDERS + 1)
    yield engine
    await engine.dispose()


async def _scalar(session: AsyncSession, sql: str, params: dict | None = None):
    return (await session.execute(text(sql), params or {})).scalar_one()


async def _queued_on_server(probe: AsyncSession, key: int) -> int:
    """How many transactions wait, in PostgreSQL's lock queue, for the advisory lock ``key``.

    A bigint advisory key shows as classid = high 32 bits, objid = low 32 bits, objsubid = 1;
    game keys fit in 32 bits. pg_locks is read live, so each read sees the queue as it is now.
    """
    count = await _scalar(
        probe,
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = 0 "
        "AND objid::bigint = :key AND objsubid = 1 AND NOT granted",
        {"key": key},
    )
    await probe.commit()
    return count


async def _until_queued(probe: AsyncSession, key: int, expected: int) -> int:
    """Wait (bounded) until ``expected`` transactions queue for ``key``; returns the count reached."""
    deadline = time.monotonic() + QUEUE_DEADLINE_SECONDS
    count = await _queued_on_server(probe, key)
    while count < expected and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
        count = await _queued_on_server(probe, key)
    return count


async def _contend(engine: AsyncEngine, game_id: str, start: asyncio.Barrier) -> float:
    """One request with its own session and connection; returns how long it waited for the lock.

    The connection is checked out and the transaction open BEFORE the start, so the
    time measured is the lock wait alone, not a connection setup.
    """
    async with AsyncSession(engine) as session:
        await session.execute(text("SELECT 1"))
        await start.wait()
        started = time.monotonic()
        async with get_game_lock(game_id, session):
            waited = time.monotonic() - started
            await asyncio.sleep(HOLD_SECONDS)
            await session.commit()
    return waited


async def _wait_in_line(engine: AsyncEngine, game_id: str, place: int, served: list[int]) -> None:
    async with AsyncSession(engine) as session, get_game_lock(game_id, session):
        served.append(place)
        await session.commit()


@pytest.mark.postgres
async def test_pg_lock_is_released_when_the_pooled_connection_goes_back(pooled_pair, monkeypatch):
    """A lock taken in a committed transaction does not stay on its pooled connection (TQ-06).

    A's connection goes back to A's pool still OPEN; B, on another pool, must then get the
    lock at once. A session-level lock would stay held by A's idle connection for as long
    as the pool keeps it, and every later move on that game would time out after 30 s.
    """
    # Prepare
    monkeypatch.setattr(game_lock, "LOCK_TIMEOUT_SECONDS", 2)  # a leak fails in 2 s, not 30
    engine_a, engine_b = pooled_pair
    game_id = str(uuid4())

    # Act
    async with AsyncSession(engine_a) as session_a, get_game_lock(game_id, session_a):
        pid_a = await _scalar(session_a, "SELECT pg_backend_pid()")
        await session_a.commit()
    async with AsyncSession(engine_b) as probe:
        locks_still_held_by_a = await _scalar(
            probe, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = :pid", {"pid": pid_a}
        )
        await probe.commit()
    started = time.monotonic()
    async with AsyncSession(engine_b) as session_b, get_game_lock(game_id, session_b):
        waited = time.monotonic() - started
        await session_b.commit()

    # Assert
    assert engine_a.pool.checkedin() == 1, "A's connection must be back in its pool, open"
    assert locks_still_held_by_a == 0
    assert waited < 1.0


@pytest.mark.postgres
async def test_pg_lock_simultaneous_moves_wait_in_a_queue_not_in_polling_steps(pooled_engine):
    """12 simultaneous moves, 5 ms each: the median wait stays well under 150 ms (BDP-06).

    The old lock retried every 100 ms with no order, so a move waited in 100 ms steps
    (median ~530 ms, the slowest over a second) while the lock sat free between polls.

    Every one of the BURSTS bursts runs, each on a game of its own, and the lowest median
    is compared with the budget: a busy machine (the suite running beside other work) can
    only lengthen a burst, never shorten one, so the fastest burst measures the lock. The
    polling lock still fails it: every contender that misses its first try sleeps 100 ms
    before the next, so a burst's median sits past 100 ms however quick the machine.
    """
    # Prepare
    medians: list[float] = []
    bursts: list[list[int]] = []

    # Act
    for _ in range(BURSTS):
        game_id = str(uuid4())
        start = asyncio.Barrier(CONTENDERS)
        waits = await asyncio.gather(*(_contend(pooled_engine, game_id, start) for _ in range(CONTENDERS)))
        medians.append(statistics.median(waits))
        bursts.append(sorted(round(w * 1000) for w in waits))

    # Assert
    assert min(medians) < MEDIAN_WAIT_BUDGET_SECONDS, bursts


@pytest.mark.postgres
async def test_pg_lock_serves_waiters_in_arrival_order(pooled_engine, monkeypatch):
    """Waiters queue in PostgreSQL and are served first come, first served.

    Each waiter is started only once the previous one is visibly queued on the server,
    so the arrival order is known; then the holder commits.
    """
    # Prepare
    monkeypatch.setattr(game_lock, "LOCK_TIMEOUT_SECONDS", 10)
    game_id = str(uuid4())
    key = _game_id_to_lock_key(game_id)
    served: list[int] = []
    queued: list[int] = []
    waiters: list[asyncio.Task[None]] = []

    # Act
    async with AsyncSession(pooled_engine) as holder, AsyncSession(pooled_engine) as probe:
        try:
            async with get_game_lock(game_id, holder):
                for place in range(QUEUED_WAITERS):
                    waiters.append(asyncio.create_task(_wait_in_line(pooled_engine, game_id, place, served)))
                    queued.append(await _until_queued(probe, key, place + 1))
                await holder.commit()
            await asyncio.gather(*waiters)
        finally:
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

    # Assert
    assert queued == list(range(1, QUEUED_WAITERS + 1)), "every waiter must queue on the server"
    assert served == list(range(QUEUED_WAITERS))


@pytest.mark.postgres
async def test_pg_lock_wait_past_the_timeout_raises_timeout_error(pooled_engine, monkeypatch):
    """A wait longer than LOCK_TIMEOUT_SECONDS raises TimeoutError; the holder keeps the lock.

    The guard below fails the test (a TimeoutError without the game id) if the wait were
    not bounded at all. PostgreSQL aborts the waiting transaction, so the caller rolls
    back — as every caller does by letting the error propagate to ``get_session``.
    """
    # Prepare
    monkeypatch.setattr(game_lock, "LOCK_TIMEOUT_SECONDS", 1)
    game_id = str(uuid4())
    key = _game_id_to_lock_key(game_id)

    async with (
        AsyncSession(pooled_engine) as holder,
        AsyncSession(pooled_engine) as contender,
        get_game_lock(game_id, holder),
    ):
        holder_pid = await _scalar(holder, "SELECT pg_backend_pid()")

        # Act
        started = time.monotonic()
        with pytest.raises(TimeoutError, match=game_id):
            async with asyncio.timeout(10), get_game_lock(game_id, contender):
                pass
        waited = time.monotonic() - started
        await contender.rollback()
        contender_usable = await _scalar(contender, "SELECT 1")
        holders = await _scalar(
            contender,
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid::bigint = :key "
            "AND granted AND pid = :pid",
            {"key": key, "pid": holder_pid},
        )
        await contender.commit()
        await holder.commit()

    # Assert
    assert 0.9 <= waited < 5.0
    assert contender_usable == 1
    assert holders == 1


@pytest.mark.postgres
async def test_pg_lock_timeout_never_outlives_the_transaction(pooled_pair):
    """lock_timeout is SET LOCAL: it bounds this transaction and leaves the connection as it was.

    The next transaction on the same pooled connection — another client, behind
    PgBouncer's transaction pooling — finds the server's own setting. A session-level
    SET would hand every later client of that server connection a 30 s lock_timeout.
    """
    # Prepare
    engine, _ = pooled_pair

    # Act
    async with AsyncSession(engine) as session:
        before = await _scalar(session, "SELECT current_setting('lock_timeout')")
        pid = await _scalar(session, "SELECT pg_backend_pid()")
        async with get_game_lock(str(uuid4()), session):
            inside = await _scalar(session, "SELECT current_setting('lock_timeout')")
            await session.commit()
    async with AsyncSession(engine) as next_client:
        next_pid = await _scalar(next_client, "SELECT pg_backend_pid()")
        after = await _scalar(next_client, "SELECT current_setting('lock_timeout')")
        await next_client.commit()

    # Assert
    assert next_pid == pid, "the second session must reuse the pooled connection"
    assert before != inside
    assert inside == f"{game_lock.LOCK_TIMEOUT_SECONDS}s"
    assert after == before


async def _lock_and_hold(session: AsyncSession, game_id: str) -> str:
    async with get_game_lock(game_id, session):
        return game_id


@pytest.mark.postgres
async def test_pg_lock_deadlock_is_broken_by_the_server_not_waited_out(pooled_engine, monkeypatch):
    """Two transactions, each holding one game's lock and waiting for the other's.

    PostgreSQL's deadlock detector aborts one of them after ``deadlock_timeout`` (1 s) and
    the other gets its lock; the polling try-lock left both to time out. The victim's error
    is deadlock_detected, not TimeoutError: only a wait that ran out is a timeout. Nothing in
    the app takes two game locks in opposite orders (room lock, then game lock), so a
    deadlock would be a bug to see in the logs, not a slow table.
    """
    # Prepare
    monkeypatch.setattr(game_lock, "LOCK_TIMEOUT_SECONDS", 10)
    first_game, second_game = str(uuid4()), str(uuid4())

    async with AsyncSession(pooled_engine) as one, AsyncSession(pooled_engine) as two:
        async with get_game_lock(first_game, one), get_game_lock(second_game, two):
            # Act
            started = time.monotonic()
            outcomes = await asyncio.gather(
                _lock_and_hold(one, second_game), _lock_and_hold(two, first_game), return_exceptions=True
            )
            elapsed = time.monotonic() - started
        await one.rollback()
        await two.rollback()

    # Assert
    errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    granted = [outcome for outcome in outcomes if isinstance(outcome, str)]
    assert len(errors) == 1, outcomes
    assert isinstance(errors[0], DBAPIError)
    assert not isinstance(errors[0], TimeoutError)
    assert getattr(errors[0].orig, "sqlstate", None) == DeadlockDetectedError.sqlstate
    assert len(granted) == 1
    assert elapsed < game_lock.LOCK_TIMEOUT_SECONDS / 2
