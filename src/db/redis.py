from typing import Any

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore

from app.config import get_settings


async def get_redis_client() -> Any:
    """Create a Redis async client from environment settings."""
    if Redis is None:
        raise RuntimeError("Redis package is not installed.")
    settings = get_settings()
    return Redis.from_url(settings.redis_url, protocol=2)
