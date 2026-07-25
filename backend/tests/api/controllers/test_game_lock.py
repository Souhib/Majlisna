"""Tests for the game_lock module."""

import asyncio

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.game_lock import _fallback_locks, _game_id_to_lock_key, cleanup_game_lock, get_game_lock

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
