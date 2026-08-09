import asyncio
import hashlib
import json
import logging
import math
import re
from collections import OrderedDict
from typing import Any

import httpx

from app.config import get_settings
from db.redis import get_redis_client

logger = logging.getLogger(__name__)

_shared_httpx: httpx.AsyncClient | None = None
_shared_httpx_loop: Any = None


async def _get_httpx_client() -> httpx.AsyncClient:
    global _shared_httpx, _shared_httpx_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _shared_httpx is not None and current_loop is not None and _shared_httpx_loop is not current_loop:
        try:
            await _shared_httpx.aclose()
        except Exception:
            pass
        _shared_httpx = None
        _shared_httpx_loop = None

    if _shared_httpx is None or _shared_httpx.is_closed:
        _shared_httpx = httpx.AsyncClient(timeout=10.0)
        _shared_httpx_loop = current_loop
    return _shared_httpx


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)





async def _get_neural_embedding(text: str) -> list[float]:
    """Generate semantic embedding via Gemini API."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key is required to generate embeddings in production.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={settings.gemini_api_key}"
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]},
    }
    client = await _get_httpx_client()
    res = await client.post(url, json=payload)
    if res.status_code == 200:
        return res.json()["embedding"]["values"]
    
    error_msg = f"Gemini embedding API returned {res.status_code}: {res.text[:200]}"
    logger.error(error_msg)
    raise ValueError(error_msg)





class SemanticCacheService:
    """Neural Vector-Similarity semantic query caching (Redis only)."""

    def __init__(self, ttl_seconds: int = 3600, default_similarity_threshold: float = 0.75) -> None:
        self._ttl = ttl_seconds
        self._similarity_threshold = default_similarity_threshold

    def _hash_key(self, prompt: str, tenant_id: str = "default") -> str:
        normalized = prompt.strip().lower()
        digest = hashlib.sha256(f"{tenant_id}:{normalized}".encode("utf-8")).hexdigest()
        return f"semantic_cache:{digest}"

    async def get(
        self, prompt: str, tenant_id: str = "default", similarity_threshold: float | None = None
    ) -> dict[str, Any] | None:
        threshold = similarity_threshold or self._similarity_threshold
        exact_key = self._hash_key(prompt, tenant_id)

        try:
            client = await get_redis_client()
            
            # 1. Exact match from Redis
            data = await client.get(exact_key)
            if data:
                item = json.loads(data)
                return item.get("payload", item)

            # 2. Neural Vector Cosine Similarity Search from Redis keys
            try:
                prompt_vec = await _get_neural_embedding(prompt)
            except Exception:
                return None
                
            best_similarity = 0.0
            best_payload: dict[str, Any] | None = None

            # Optimization: only scan a limited set of recent semantic keys in a real prod env
            # For this MVP prod version we scan semantic_cache:* keys (this can be slow if large)
            keys = await client.keys("semantic_cache:*")
            if not keys:
                return None
                
            values = await client.mget(keys)
            for val in values:
                if val:
                    entry = json.loads(val)
                    if entry.get("tenant_id") == tenant_id and "embedding" in entry:
                        cached_vec = entry["embedding"]
                        if len(cached_vec) == len(prompt_vec):
                            sim = _cosine_similarity(prompt_vec, cached_vec)
                            if sim > best_similarity:
                                best_similarity = sim
                                best_payload = entry.get("payload")

            if best_similarity >= threshold and best_payload is not None:
                return best_payload
                
        except Exception as exc:
            logger.error("Redis exact lookup failed: %s", exc)

        return None

    async def set(
        self, prompt: str, payload: dict[str, Any], tenant_id: str = "default"
    ) -> None:
        try:
            embedding = await _get_neural_embedding(prompt)
            key = self._hash_key(prompt, tenant_id)
            entry = {
                "prompt": prompt,
                "tenant_id": tenant_id,
                "embedding": embedding,
                "payload": payload,
            }
            encoded = json.dumps(entry, default=str)
            client = await get_redis_client()
            await client.set(key, encoded, ex=self._ttl)
        except Exception as exc:
            logger.error("Redis cache set failed: %s", exc)

    async def delete(self, prompt: str, tenant_id: str = "default") -> None:
        try:
            key = self._hash_key(prompt, tenant_id)
            client = await get_redis_client()
            await client.delete(key)
        except Exception as exc:
            logger.error("Redis cache delete failed: %s", exc)

    async def flush_all(self) -> None:
        try:
            client = await get_redis_client()
            keys = await client.keys("semantic_cache:*")
            if keys:
                await client.delete(*keys)
        except Exception as exc:
            logger.error("Redis cache flush failed: %s", exc)


semantic_cache_service = SemanticCacheService()


async def get_semantic_cache(
    prompt: str, tenant_id: str = "default", similarity_threshold: float = 0.75
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
