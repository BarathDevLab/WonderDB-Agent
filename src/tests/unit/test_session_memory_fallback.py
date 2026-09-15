import pytest

import services.session_memory as memory_module
from services.session_memory import SessionMemoryService


class BrokenRedis:
    async def rpush(self, *args):
        raise ConnectionError("redis down")

    async def expire(self, *args):
        raise ConnectionError("redis down")

    async def lrange(self, *args):
        raise ConnectionError("redis down")

    async def delete(self, *args):
        raise ConnectionError("redis down")


@pytest.mark.asyncio
async def test_session_history_survives_redis_outage_in_process(monkeypatch) -> None:
    service = SessionMemoryService()

    async def broken_client():
        return BrokenRedis()

    monkeypatch.setattr(memory_module, "get_redis_client", broken_client)
    await service.append_session_event("chat-1", {
        "phase": "summary", "prompt": "Show revenue", "summary": "Revenue is 100.",
    })

    assert await service.get_session_history("chat-1") == [{
        "phase": "summary", "prompt": "Show revenue", "summary": "Revenue is 100.",
    }]


@pytest.mark.asyncio
async def test_local_fallback_is_bounded(monkeypatch) -> None:
    service = SessionMemoryService(max_local_sessions=2, max_events_per_session=2)

    async def broken_client():
        return BrokenRedis()

    monkeypatch.setattr(memory_module, "get_redis_client", broken_client)
    for value in range(3):
        await service.append_session_event("chat-1", {"value": value})
    await service.append_session_event("chat-2", {"value": 2})
    await service.append_session_event("chat-3", {"value": 3})

    assert await service.get_session_history("chat-1") == []
    assert await service.get_session_history("chat-3") == [{"value": 3}]
