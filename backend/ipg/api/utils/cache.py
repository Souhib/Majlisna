import time
from typing import TypeVar

T = TypeVar("T")


class TTLCache:
    """Simple in-memory cache with time-to-live expiration.

    Uses monotonic clock for reliable timing regardless of system clock changes.
    Thread-safe for reads; intended for caching near-static data (word pairs, achievements, etc.).
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
        """Cache a value with a TTL in seconds."""
        self._store[key] = (time.monotonic() + ttl_seconds, value)

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
