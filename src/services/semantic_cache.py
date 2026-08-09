import hashlib
import json
import math
import re
from typing import Any
from db.redis import get_redis_client


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _pseudo_dense_embedding(text: str, dimensions: int = 1536) -> list[float]:
    tokens = re.findall(r"\w+", text.lower())
    vec = [0.0] * dimensions
    for i, token in enumerate(tokens):
        token_hash = hash(token)
        idx = abs(token_hash) % dimensions
        weight = 1.0 / (1.0 + math.log(1 + i))
        vec[idx] += weight
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


class SemanticCacheService:
    """Vector-similarity and exact match semantic query caching service."""

    def __init__(self, ttl_seconds: int = 3600, default_similarity_threshold: float = 0.85) -> None:
        self._ttl = ttl_seconds
        self._similarity_threshold = default_similarity_threshold
        # In-memory index of entries: key -> {prompt, embedding, payload, tenant_id}
        self._local_cache: dict[str, dict[str, Any]] = {}

    def _hash_key(self, prompt: str, tenant_id: str = "default") -> str:
        normalized = prompt.strip().lower()
        digest = hashlib.sha256(f"{tenant_id}:{normalized}".encode("utf-8")).hexdigest()
        return f"semantic_cache:{digest}"

    async def get(
        self, prompt: str, tenant_id: str = "default", similarity_threshold: float | None = None
    ) -> dict[str, Any] | None:
        threshold = similarity_threshold or self._similarity_threshold
        prompt_vec = _pseudo_dense_embedding(prompt)
        exact_key = self._hash_key(prompt, tenant_id)

        # 1. Check exact key in Redis / local memory
        try:
            client = await get_redis_client()
            async with client:
                data = await client.get(exact_key)
                if data:
                    item = json.loads(data)
                    return item.get("payload", item)
        except Exception:
            if exact_key in self._local_cache:
                return self._local_cache[exact_key].get("payload", self._local_cache[exact_key])

        # 2. Semantic Vector Similarity Search against cached entries
        best_similarity = 0.0
        best_payload: dict[str, Any] | None = None

        # Inspect local cache
        for entry in self._local_cache.values():
            if entry.get("tenant_id") == tenant_id and "embedding" in entry:
                sim = _cosine_similarity(prompt_vec, entry["embedding"])
                if sim > best_similarity:
                    best_similarity = sim
                    best_payload = entry.get("payload")

        if best_similarity >= threshold and best_payload is not None:
            return best_payload

        # Inspect Redis keys if available
        try:
            client = await get_redis_client()
            async with client:
                keys = await client.keys("semantic_cache:*")
                for k in keys:
                    raw = await client.get(k)
                    if raw:
                        entry = json.loads(raw)
                        if entry.get("tenant_id") == tenant_id and "embedding" in entry:
                            sim = _cosine_similarity(prompt_vec, entry["embedding"])
                            if sim > best_similarity:
                                best_similarity = sim
                                best_payload = entry.get("payload")
            if best_similarity >= threshold and best_payload is not None:
                return best_payload
        except Exception:
            pass

        return None

    async def set(
        self, prompt: str, payload: dict[str, Any], tenant_id: str = "default"
    ) -> None:
        key = self._hash_key(prompt, tenant_id)
        embedding = _pseudo_dense_embedding(prompt)
        entry = {
            "prompt": prompt,
            "tenant_id": tenant_id,
            "embedding": embedding,
            "payload": payload,
        }
        encoded = json.dumps(entry, default=str)
        self._local_cache[key] = entry
        try:
            client = await get_redis_client()
            async with client:
                await client.set(key, encoded, ex=self._ttl)
        except Exception:
            pass

    async def delete(self, prompt: str, tenant_id: str = "default") -> None:
        key = self._hash_key(prompt, tenant_id)
        self._local_cache.pop(key, None)
        try:
            client = await get_redis_client()
            async with client:
                await client.delete(key)
        except Exception:
            pass

    async def flush_all(self) -> None:
        self._local_cache.clear()
        try:
            client = await get_redis_client()
            async with client:
                keys = await client.keys("semantic_cache:*")
                if keys:
                    await client.delete(*keys)
        except Exception:
            pass


semantic_cache_service = SemanticCacheService()


async def get_semantic_cache(
    prompt: str, tenant_id: str = "default", similarity_threshold: float = 0.85
) -> dict[str, Any] | None:
    return await semantic_cache_service.get(prompt, tenant_id, similarity_threshold)


async def delete_semantic_cache(prompt: str, tenant_id: str = "default") -> None:
    await semantic_cache_service.delete(prompt, tenant_id)


async def flush_semantic_cache() -> None:
    await semantic_cache_service.flush_all()


async def set_semantic_cache(
    prompt: str, payload: dict[str, Any], tenant_id: str = "default"
) -> None:
    await semantic_cache_service.set(prompt, payload, tenant_id)
