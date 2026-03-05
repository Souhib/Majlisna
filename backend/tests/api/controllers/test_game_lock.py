"""Tests for the game_lock module."""

from ipg.api.controllers.game_lock import _fallback_locks, cleanup_game_lock, get_game_lock


class TestGetGameLock:
    def setup_method(self):
        """Clear the global lock dict before each test."""
        _fallback_locks.clear()

    async def test_creates_lock_on_use(self):
        """get_game_lock creates a fallback asyncio.Lock when no Redis is configured."""
        # Act
        async with get_game_lock("game-1"):
            pass

        # Assert
        assert "game-1" in _fallback_locks

    async def test_returns_same_lock_for_same_id(self):
        """get_game_lock reuses the same fallback Lock for the same game_id."""
        # Act
        async with get_game_lock("game-1"):
            lock1 = _fallback_locks["game-1"]
        async with get_game_lock("game-1"):
            lock2 = _fallback_locks["game-1"]

        # Assert
        assert lock1 is lock2

    async def test_returns_different_locks_for_different_ids(self):
        """Different game_ids get independent fallback locks."""
        # Act
        async with get_game_lock("game-a"):
            pass
        async with get_game_lock("game-b"):
            pass

        # Assert
        assert _fallback_locks["game-a"] is not _fallback_locks["game-b"]


class TestCleanupGameLock:
    def setup_method(self):
        _fallback_locks.clear()

    async def test_removes_existing_lock(self):
        """cleanup_game_lock removes a lock that was previously created."""
        # Prepare
        async with get_game_lock("game-1"):
            pass
        assert "game-1" in _fallback_locks

        # Act
        cleanup_game_lock("game-1")

        # Assert
        assert "game-1" not in _fallback_locks

    def test_nonexistent_no_error(self):
        """cleanup_game_lock does not raise when the game_id doesn't exist."""
        # Act / Assert — should not raise
        cleanup_game_lock("nonexistent-id")
