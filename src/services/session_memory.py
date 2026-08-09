import json
from typing import Any
from db.redis import get_redis_client


class SessionMemoryService:
    """Session history and conversational memory manager backed by Redis with in-memory fallback."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._fallback_memory: dict[str, list[dict[str, Any]]] = {}

    async def append_session_event(self, session_id: str, event: dict[str, Any]) -> None:
        key = f"session:{session_id}:events"
        payload = json.dumps(event)

        try:
            client = await get_redis_client()
            async with client:
                await client.rpush(key, payload)
                await client.expire(key, self._ttl)
        except Exception:
            # Resilient fallback to local memory if Redis is not running
            if session_id not in self._fallback_memory:
                self._fallback_memory[session_id] = []
            self._fallback_memory[session_id].append(event)

    async def get_session_history(
        self, session_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        key = f"session:{session_id}:events"

        try:
            client = await get_redis_client()
            async with client:
                raw_events = await client.lrange(key, -limit, -1)
                return [json.loads(e) for e in raw_events]
        except Exception:
            events = self._fallback_memory.get(session_id, [])
            return events[-limit:]


session_memory_service = SessionMemoryService()


async def append_session_event(session_id: str, event: dict[str, Any]) -> None:
    await session_memory_service.append_session_event(session_id, event)
