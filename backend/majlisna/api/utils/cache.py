import time
from typing import TypeVar

T = TypeVar("T")


# Hard ceiling on entries. Reached only by per-entity keys (one per user, per word
# pack, …), never by the handful of global ones.
MAX_ENTRIES = 5_000


class TTLCache:
    """Simple in-memory cache with time-to-live expiration.

    Uses monotonic clock for reliable timing regardless of system clock changes.
    Intended for near-static data (word pairs, achievement definitions, leaderboards).

    **Per-process.** Each uvicorn worker has its own instance, so `invalidate()`
    only reaches the worker that calls it — never cache anything whose staleness
    matters beyond its TTL. That is why user stats are no longer cached here (a
    `user_stats` entry survived a game end on three of four workers) and why
    `CACHE_TTL_LEADERBOARD_SECONDS` is short: for the leaderboard the TTL, not the
    invalidation, is the real freshness bound.

    **Never cache SQLAlchemy ORM instances.** They belong to the session that
    loaded them; handing one to a later request means a detached object shared
    across sessions, and touching an unloaded attribute raises
    `DetachedInstanceError`. Cache plain values or Pydantic models.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        """Get a cached value if it exists and hasn't expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: object, ttl_seconds: float) -> None:
        """Cache a value with a TTL in seconds, evicting expired entries when full."""
        if len(self._store) >= MAX_ENTRIES and key not in self._store:
            self._evict()
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    def _evict(self) -> None:
        """Drop expired entries, then the soonest-to-expire if that wasn't enough.

        Entries were only ever removed when someone read them back, so a key that is
        written once and never read again — `user_stats:{id}` for a player who does
        not return — stayed resident for the life of the worker. That is a slow leak
        in each of them.
        """
        now = time.monotonic()
        for key in [k for k, (expires_at, _) in self._store.items() if expires_at <= now]:
            del self._store[key]
        if len(self._store) < MAX_ENTRIES:
            return
        for key in sorted(self._store, key=lambda k: self._store[k][0])[: MAX_ENTRIES // 10]:
            del self._store[key]

    def invalidate(self, key: str) -> None:
        """Remove a specific key from the cache."""
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys starting with the given prefix."""
        keys_to_remove = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._store[k]

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()


# Singleton cache instance
cache = TTLCache()
