import json

import pytest

import agent.mcp_client as mcp_client
import services.execution_control as execution_control
import services.semantic_cache as cache_module
from services.execution_control import (
    load_execution_checkpoint,
    request_fingerprint,
    save_execution_checkpoint,
    schema_fingerprint,
)
from services.semantic_cache import SemanticCacheService


class MemoryRedis:
    def __init__(self) -> None:
        self.values = {}

    async def set(self, key, value, ex=None):
        del ex
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)


def test_schema_and_request_fingerprints_are_stable_and_scoped() -> None:
    schema_a = [{"table_name": "orders", "columns": [{"name": "id", "type": "uuid"}]}]
    schema_b = [{"columns": [{"type": "uuid", "name": "id"}], "table_name": "orders"}]
    assert schema_fingerprint(schema_a) == schema_fingerprint(schema_b)
    assert request_fingerprint(
        tenant_id="a", user_id="u", session_id="s", prompt="Show   Sales",
    ) == request_fingerprint(
        tenant_id="a", user_id="u", session_id="s", prompt="show sales",
    )
    assert request_fingerprint(
        tenant_id="a", user_id="u", session_id="s", prompt="show sales",
    ) != request_fingerprint(
        tenant_id="b", user_id="u", session_id="s", prompt="show sales",
    )


@pytest.mark.asyncio
async def test_checkpoint_round_trip(monkeypatch) -> None:
    redis = MemoryRedis()

    async def fake_client():
        return redis

    monkeypatch.setattr(execution_control, "get_redis_client", fake_client)
    await save_execution_checkpoint("req-1", {"status": "running", "last_node": "sql"})
    assert await load_execution_checkpoint("req-1") == {
        "status": "running", "last_node": "sql",
    }


@pytest.mark.asyncio
async def test_cache_rejects_exact_hit_from_an_old_schema(monkeypatch) -> None:
    redis = MemoryRedis()
    service = SemanticCacheService()
    key = service._hash_key("show sales", "tenant-a")
    redis.values[key] = json.dumps({
        "cache_schema_version": cache_module._CACHE_SCHEMA_VERSION,
        "payload": {"summary": "stale", "schema_fingerprint": "old"},
    })

    async def fake_client():
        return redis

    monkeypatch.setattr(cache_module, "get_redis_client", fake_client)
    result = await service.get(
        "show sales", "tenant-a", exact_only=True, schema_fingerprint="new",
    )
    assert result is None


@pytest.mark.asyncio
async def test_mcp_call_restarts_dead_transport_once(monkeypatch) -> None:
    class DeadSession:
        async def call_tool(self, name, arguments):
            del name, arguments
            raise ConnectionError("closed")

    class LiveSession:
        async def call_tool(self, name, arguments):
            return {"tool": name, "arguments": arguments}

    dead = DeadSession()
    live = LiveSession()
    mcp_client._mcp_session = dead
    mcp_client._mcp_verified_version = mcp_client.MCP_SERVER_PROTOCOL_VERSION
    lifecycle = []

    async def fake_stop():
        lifecycle.append("stop")

    async def fake_start():
        lifecycle.append("start")
        mcp_client._mcp_session = live
        mcp_client._mcp_verified_version = mcp_client.MCP_SERVER_PROTOCOL_VERSION

    monkeypatch.setattr(mcp_client, "stop_mcp_client", fake_stop)
    monkeypatch.setattr(mcp_client, "start_mcp_client", fake_start)
    result = await mcp_client.call_mcp_tool("get_schema", {})

    assert result == {"tool": "get_schema", "arguments": {}}
    assert lifecycle == ["stop", "start"]
    mcp_client._mcp_session = None
    mcp_client._mcp_verified_version = None
