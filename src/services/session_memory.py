import json
import logging
from typing import Any

from db.redis import get_redis_client

logger = logging.getLogger(__name__)




class SessionMemoryService:
    """Session history manager backed by Redis."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds

    async def append_session_event(self, session_id: str, event: dict[str, Any]) -> None:
        key = f"session:{session_id}:events"
        payload = json.dumps(event, default=str)

        try:
            client = await get_redis_client()
            await client.rpush(key, payload)
            await client.expire(key, self._ttl)
        except Exception as exc:
            logger.error("Redis session append failed: %s", exc)

    async def get_session_history(
        self, session_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        key = f"session:{session_id}:events"

        try:
            client = await get_redis_client()
            raw_events = await client.lrange(key, -limit, -1)
            return [json.loads(e) for e in raw_events]
        except Exception as exc:
            logger.error("Redis session read failed: %s", exc)
            return []


    async def clear_session(self, session_id: str) -> None:
        key = f"session:{session_id}:events"
        try:
            client = await get_redis_client()
            await client.delete(key)
        except Exception as exc:
            logger.error("Redis session clear failed: %s", exc)


session_memory_service = SessionMemoryService()


async def append_session_event(session_id: str, event: dict[str, Any]) -> None:
    await session_memory_service.append_session_event(session_id, event)


async def clear_session_events(session_id: str) -> None:
    await session_memory_service.clear_session(session_id)


async def get_session_history(session_id: str, limit: int = 20) -> list[dict]:
    """Return the last `limit` session events for contextual follow-ups."""
    return await session_memory_service.get_session_history(session_id, limit=limit)
