import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from loguru import logger
from redis.asyncio import Redis

_redis: Redis | None = None
_fallback_locks: dict[str, asyncio.Lock] = {}


async def init_redis(url: str) -> None:
    """Initialize the Redis connection for distributed locks."""
    global _redis  # noqa: PLW0603
    if not url:
        logger.info("No REDIS_URL configured — using in-process asyncio locks")
        return
    try:
        _redis = Redis.from_url(url, decode_responses=True)
        await _redis.ping()
        logger.info("Redis connected for distributed game locks")
    except Exception:
        logger.warning("Redis unavailable — falling back to in-process asyncio locks")
        _redis = None


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis  # noqa: PLW0603
    if _redis is not None:
        await _redis.aclose()
        _redis = None


@asynccontextmanager
async def get_game_lock(game_id: str) -> AsyncGenerator[None, None]:
    """Get a distributed lock for a specific game_id.

    Uses Redis if available, otherwise falls back to asyncio.Lock.
    """
    if _redis is not None:
        lock = _redis.lock(f"game_lock:{game_id}", timeout=30)
        try:
            await lock.acquire()
            yield
        finally:
            with suppress(Exception):
                await lock.release()
    else:
        if game_id not in _fallback_locks:
            _fallback_locks[game_id] = asyncio.Lock()
        async with _fallback_locks[game_id]:
            yield


def cleanup_game_lock(game_id: str) -> None:
    """Remove the fallback lock for a game_id when the game is finished."""
    _fallback_locks.pop(game_id, None)
