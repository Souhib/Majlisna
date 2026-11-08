import asyncio
import hashlib
from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from asyncpg.exceptions import LockNotAvailableError
from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
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


def _game_id_to_lock_key(game_id: str) -> int:
    """Convert a game_id (UUID string) to a 32-bit integer for pg_advisory_xact_lock."""
    return int(hashlib.md5(game_id.encode()).hexdigest()[:8], 16)


async def _acquire_advisory_xact_lock(session: AsyncSession, game_id: str) -> None:
    """Wait for ``game_id``'s transaction-scoped advisory lock, at most ``LOCK_TIMEOUT_SECONDS``.

    ``pg_advisory_xact_lock`` BLOCKS: a waiter sleeps in PostgreSQL's lock queue and is
    woken the moment the holder commits or rolls back, first come, first served. It
    replaced a ``pg_try_advisory_xact_lock`` retried every 100 ms (BDP-06), which served
    no order and left the lock idle between polls: 12 simultaneous moves waited ~530 ms at
    the median, the slowest over a second. A waiter holds its connection (a PgBouncer
    server slot) either way. A real deadlock is now broken by PostgreSQL after
    ``deadlock_timeout`` (deadlock_detected, raised as is) instead of being waited out.

    The wait is bounded by ``lock_timeout``, set TRANSACTION-LOCAL (``set_config(...,
    true)`` is ``SET LOCAL``: under PgBouncer's transaction pooling a session-level SET
    would stay on the server connection for its next client). A wait that runs out aborts
    the transaction with lock_not_available, raised as ``TimeoutError``; the caller rolls
    back (letting the error propagate does: ``get_session`` and every ``async with
    AsyncSession``).

    The setting is NOT put back once the lock is held: that would be one more round trip
    inside the critical section, which every queued move pays in turn (on a loaded
    machine, 12 contenders waited a median of ~60-100 ms without it, ~70-190 ms with it). So
    the rest of the transaction runs under the same bound, which is the better default
    anyway: a row lock that does not come within ``LOCK_TIMEOUT_SECONDS`` fails the request instead of
    holding its PgBouncer slot for good (production runs with no statement_timeout and
    no idle_in_transaction_session_timeout). A nested lock (room, then game) sets it again.

    Transaction-scoped, released by the commit or the rollback. Never the session-level
    ``pg_advisory_lock``: it survives the commit on a pooled connection, and every later
    move on that game would wait for good (TQ-06; test_game_lock's pooled-engine tests).
    """
    lock_key = _game_id_to_lock_key(game_id)
    # `execute`, not `exec`: SQLModel deprecates it in favour of `exec`, but `exec` is
    # typed for Select statements only and cannot carry raw SQL with bound parameters.
    await session.execute(  # ty: ignore[deprecated]
        text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": f"{LOCK_TIMEOUT_SECONDS}s"}
    )
    try:
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})  # ty: ignore[deprecated]
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != LockNotAvailableError.sqlstate:
            raise
        logger.error(f"Failed to acquire advisory lock for {game_id} (key={lock_key}) after {LOCK_TIMEOUT_SECONDS}s")
        raise TimeoutError(f"Could not acquire game lock for {game_id}") from exc


@asynccontextmanager
async def get_game_lock(game_id: str, session: AsyncSession | None = None) -> AsyncGenerator[None]:
    """Acquire a lock for a specific game_id to serialize mutations.

    Uses PostgreSQL advisory locks when a session is provided (production): a blocking,
    transaction-scoped lock, held until the caller's commit or rollback (so the caller
    commits ONCE, inside the ``async with``). A wait past ``LOCK_TIMEOUT_SECONDS`` raises
    ``TimeoutError``. Falls back to in-process asyncio.Lock otherwise (SQLite / tests).
    """
    if session is not None:
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect == "postgresql":
            await _acquire_advisory_xact_lock(session, game_id)
            yield  # xact locks auto-release on commit/rollback
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
