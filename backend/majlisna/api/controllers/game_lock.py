import asyncio
import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import LOCK_TIMEOUT_SECONDS

_fallback_locks: dict[str, asyncio.Lock] = {}

LOCK_RETRY_INTERVAL = 0.1


def _game_id_to_lock_key(game_id: str) -> int:
    """Convert a game_id (UUID string) to a 32-bit integer for pg_advisory_lock."""
    return int(hashlib.md5(game_id.encode()).hexdigest()[:8], 16)


@asynccontextmanager
async def get_game_lock(game_id: str, session: AsyncSession | None = None) -> AsyncGenerator[None, None]:
    """Acquire a lock for a specific game_id to serialize mutations.

    Uses PostgreSQL advisory locks when a session is provided (production).
    Falls back to in-process asyncio.Lock otherwise (SQLite / tests).
    """
    if session is not None:
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect == "postgresql":
            lock_key = _game_id_to_lock_key(game_id)
            elapsed = 0.0
            while elapsed < LOCK_TIMEOUT_SECONDS:
                result = await session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_key})
                acquired = result.scalar()
                if acquired:
                    break
                await asyncio.sleep(LOCK_RETRY_INTERVAL)
                elapsed += LOCK_RETRY_INTERVAL
            else:
                logger.error(
                    f"Failed to acquire advisory lock for {game_id} (key={lock_key}) after {LOCK_TIMEOUT_SECONDS}s"
                )
                raise TimeoutError(f"Could not acquire game lock for {game_id}")
            try:
                yield
            finally:
                pass  # xact locks auto-release on commit/rollback
            return

    # Fallback: in-process asyncio.Lock (SQLite, tests, or no session)
    if game_id not in _fallback_locks:
        _fallback_locks[game_id] = asyncio.Lock()
    async with _fallback_locks[game_id]:
        yield


def cleanup_game_lock(game_id: str) -> None:
    """Remove the fallback lock for a game_id when the game is finished."""
    _fallback_locks.pop(game_id, None)
