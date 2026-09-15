import json
import logging
from collections import OrderedDict
from typing import Any

from db.redis import get_redis_client

logger = logging.getLogger(__name__)




class SessionMemoryService:
    """Session history manager backed by Redis with a bounded local fallback."""

    def __init__(
        self,
        ttl_seconds: int = 86400,
        max_local_sessions: int = 500,
        max_events_per_session: int = 100,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_local_sessions = max_local_sessions
        self._max_events_per_session = max_events_per_session
        self._local_events: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    def _append_local(self, session_id: str, event: dict[str, Any]) -> None:
        events = self._local_events.setdefault(session_id, [])
        events.append(dict(event))
        del events[:-self._max_events_per_session]
        self._local_events.move_to_end(session_id)
        while len(self._local_events) > self._max_local_sessions:
            self._local_events.popitem(last=False)

    def _get_local(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        events = self._local_events.get(session_id, [])
        if events:
            self._local_events.move_to_end(session_id)
        return [dict(event) for event in events[-limit:]]

    async def append_session_event(self, session_id: str, event: dict[str, Any]) -> None:
        key = f"session:{session_id}:events"
        payload = json.dumps(event, default=str)
        self._append_local(session_id, event)

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
            persisted = [json.loads(e) for e in raw_events]
            return persisted or self._get_local(session_id, limit)
        except Exception as exc:
            logger.error("Redis session read failed: %s", exc)
            return self._get_local(session_id, limit)


    async def clear_session(self, session_id: str) -> None:
        key = f"session:{session_id}:events"
        self._local_events.pop(session_id, None)
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
