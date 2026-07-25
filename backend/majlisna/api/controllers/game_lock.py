import asyncio
import hashlib
from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from loguru import logger
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import LOCK_TIMEOUT_SECONDS

# Weak-valued on purpose: an entry disappears as soon as nothing is using the lock.
#
# This was a plain dict that grew one entry per game forever — `cleanup_game_lock`
# exists to purge it but had no caller anywhere in the app, which made the leak look
# handled. A WeakValueDictionary needs no caller: the only strong reference to a lock
# is the `async with` below, so the entry survives exactly as long as some task holds
# or awaits it. (Only SQLite/dev reaches this path; PostgreSQL uses advisory locks.)
_fallback_locks: MutableMapping[str, asyncio.Lock] = WeakValueDictionary()

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

    # Fallback: in-process asyncio.Lock (SQLite, tests, or no session).
    #
    # The local `lock` variable is what keeps the entry alive in the weak map — a
    # second lookup instead of a local would race the garbage collector between the
    # insert and the `async with`. There is no await between the two statements, so
    # no other task can interleave here.
    lock = _fallback_locks.get(game_id)
    if lock is None:
        lock = asyncio.Lock()
        _fallback_locks[game_id] = lock
    async with lock:
        yield


def cleanup_game_lock(game_id: str) -> None:
    """Drop the fallback lock for a game_id.

    No longer required for correctness — `_fallback_locks` is weak-valued, so an
    unused lock is collected on its own. Kept because it is harmless and makes the
    intent explicit at a call site that knows a game is over.
    """
    _fallback_locks.pop(game_id, None)
