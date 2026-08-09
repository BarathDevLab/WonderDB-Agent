import hashlib
import json
from typing import Any
from db.redis import get_redis_client


class SemanticCacheService:
    """Fast semantic and exact match query caching service."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._local_cache: dict[str, dict[str, Any]] = {}

    def _hash_key(self, prompt: str, tenant_id: str = "default") -> str:
        normalized = prompt.strip().lower()
        digest = hashlib.sha256(f"{tenant_id}:{normalized}".encode("utf-8")).hexdigest()
        return f"semantic_cache:{digest}"

    async def get(self, prompt: str, tenant_id: str = "default") -> dict[str, Any] | None:
        key = self._hash_key(prompt, tenant_id)
        try:
            client = await get_redis_client()
            async with client:
                data = await client.get(key)
                if data:
                    return json.loads(data)
        except Exception:
            return self._local_cache.get(key)
        return None

    async def set(
        self, prompt: str, payload: dict[str, Any], tenant_id: str = "default"
    ) -> None:
        key = self._hash_key(prompt, tenant_id)
        encoded = json.dumps(payload, default=str)
        try:
            client = await get_redis_client()
            async with client:
                await client.set(key, encoded, ex=self._ttl)
        except Exception:
            self._local_cache[key] = payload

    async def delete(self, prompt: str, tenant_id: str = "default") -> None:
        key = self._hash_key(prompt, tenant_id)
        self._local_cache.pop(key, None)
        try:
            client = await get_redis_client()
            async with client:
                await client.delete(key)
        except Exception:
            pass


semantic_cache_service = SemanticCacheService()


async def get_semantic_cache(prompt: str, tenant_id: str = "default") -> dict[str, Any] | None:
    return await semantic_cache_service.get(prompt, tenant_id)


async def delete_semantic_cache(prompt: str, tenant_id: str = "default") -> None:
    await semantic_cache_service.delete(prompt, tenant_id)


async def set_semantic_cache(
    prompt: str, payload: dict[str, Any], tenant_id: str = "default"
) -> None:
    await semantic_cache_service.set(prompt, payload, tenant_id)
