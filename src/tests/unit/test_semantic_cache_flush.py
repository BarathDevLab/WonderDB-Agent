import pytest

import services.semantic_cache as semantic_cache_module
from services.semantic_cache import SemanticCacheService


class FakeRedis:
    def __init__(self, keys: list[str], ping_error: Exception | None = None) -> None:
        self.keys = set(keys)
        self.ping_error = ping_error
        self.delete_calls: list[tuple[str, ...]] = []

    async def ping(self) -> bool:
        if self.ping_error:
            raise self.ping_error
        return True

    async def get(self, key: str):
        del key
        return None

    async def scan_iter(self, match: str, count: int = 10):
        del count
        prefix = match.removesuffix("*")
        # Snapshot semantics expose the bug caused by deleting during iteration.
        for key in list(self.keys):
            if key.startswith(prefix):
                yield key

    async def delete(self, *keys: str) -> int:
        self.delete_calls.append(keys)
        deleted = sum(key in self.keys for key in keys)
        self.keys.difference_update(keys)
        return deleted


@pytest.mark.asyncio
async def test_flush_collects_deletes_and_verifies_semantic_keys(monkeypatch) -> None:
    redis = FakeRedis([
        "semantic_cache:first",
        "semantic_cache:second",
        "semantic_cache:third",
        "session:keep-this",
    ])

    async def fake_client() -> FakeRedis:
        return redis

    monkeypatch.setattr(semantic_cache_module, "get_redis_client", fake_client)
    result = await SemanticCacheService().flush_all()

    assert result == {"deleted": 3, "remaining": 0}
    assert redis.keys == {"session:keep-this"}
    assert {key for call in redis.delete_calls for key in call} == {
        "semantic_cache:first",
        "semantic_cache:second",
        "semantic_cache:third",
    }


@pytest.mark.asyncio
async def test_flush_propagates_redis_failure(monkeypatch) -> None:
    redis = FakeRedis([], ping_error=ConnectionError("Redis unavailable"))

    async def fake_client() -> FakeRedis:
        return redis

    monkeypatch.setattr(semantic_cache_module, "get_redis_client", fake_client)

    with pytest.raises(ConnectionError, match="Redis unavailable"):
        await SemanticCacheService().flush_all()


@pytest.mark.asyncio
async def test_contextual_exact_lookup_does_not_run_similarity_search(monkeypatch) -> None:
    redis = FakeRedis(["semantic_cache:unrelated"])

    async def fake_client() -> FakeRedis:
        return redis

    async def unexpected_embedding(prompt: str):
        raise AssertionError(f"Embedding should not be called for exact-only lookup: {prompt}")

    monkeypatch.setattr(semantic_cache_module, "get_redis_client", fake_client)
    monkeypatch.setattr(semantic_cache_module, "_get_neural_embedding", unexpected_embedding)

    result = await SemanticCacheService().get(
        "resolved conversational prompt", "tenant-a", exact_only=True,
    )

    assert result is None
