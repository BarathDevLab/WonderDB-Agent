import asyncio
import logging
from typing import Any

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool: Any = None
_redis_loop: asyncio.AbstractEventLoop | None = None


async def get_redis_client() -> Any:
    """Return a shared Redis connection pool (singleton with explicit loop-safety)."""
    global _redis_pool, _redis_loop
    if Redis is None:
        raise RuntimeError("Redis package is not installed.")

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_pool is not None and current_loop is not None and _redis_loop is not current_loop:
        try:
            if hasattr(_redis_pool, "aclose"):
                await _redis_pool.aclose()
            else:
                await _redis_pool.close()
        except Exception:
            pass
        _redis_pool = None
        _redis_loop = None

    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = Redis.from_url(
            settings.redis_url,
            protocol=2,
            decode_responses=True,
            max_connections=20,
        )
        _redis_loop = current_loop
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool, _redis_loop
    if _redis_pool is not None:
        try:
            if hasattr(_redis_pool, "aclose"):
                await _redis_pool.aclose()
            else:
                await _redis_pool.close()
        except Exception:
            pass
        _redis_pool = None
        _redis_loop = None
