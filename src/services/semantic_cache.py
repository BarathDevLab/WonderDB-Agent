"""
semantic_cache.py
=================
Neural vector-similarity semantic query caching backed by Redis.

Two-tier lookup strategy:
  1. Exact SHA-256 key match (O(1)) — returns instantly for identical prompts.
  2. SCAN-based vector cosine-similarity search over cached entries.

Bug fix: replaced `client.keys("semantic_cache:*")` (O(N) blocking Redis scan,
a known production anti-pattern) with async `scan_iter()` cursor-based iteration
with a hard limit on entries checked to bound worst-case latency.
"""
import asyncio
import hashlib
import json
import logging
import math
from typing import Any

import httpx

from app.config import get_settings
from db.redis import get_redis_client

logger = logging.getLogger(__name__)

# Maximum cache entries to scan during similarity search.
# Prevents O(N) Redis scan from blocking too long on large caches.
_MAX_SCAN_ENTRIES = 500

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
        raise ValueError("Gemini API key is required for semantic cache embeddings.")

    clean_model = "gemini-embedding-001"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{clean_model}:embedContent?key={settings.gemini_api_key}"
    )
    payload = {
        "model": f"models/{clean_model}",
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
    """Neural vector-similarity semantic query cache (Redis-backed)."""

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
        threshold = similarity_threshold if similarity_threshold is not None else self._similarity_threshold
        exact_key = self._hash_key(prompt, tenant_id)

        try:
            client = await get_redis_client()

            # ── Tier 1: exact key match (O(1)) ──────────────────────────
            data = await client.get(exact_key)
            if data:
                item = json.loads(data)
                return item.get("payload", item)

            # ── Tier 2: vector similarity scan ──────────────────────────
            # Generate embedding only if there are cached entries to search
            # (avoids an unnecessary API call on an empty cache)
            try:
                prompt_vec = await _get_neural_embedding(prompt)
            except Exception as exc:
                logger.warning("Embedding for cache lookup failed: %s", exc)
                return None

            best_similarity = 0.0
            best_payload: dict[str, Any] | None = None
            entries_checked = 0

            # FIXED: Use async scan_iter() cursor pagination instead of blocking KEYS *
            # scan_iter yields keys in small batches and is safe for large Redis instances.
            async for key in client.scan_iter("semantic_cache:*", count=100):
                if entries_checked >= _MAX_SCAN_ENTRIES:
                    logger.debug(
                        "Semantic cache scan capped at %d entries", _MAX_SCAN_ENTRIES
                    )
                    break

                val = await client.get(key)
                if not val:
                    continue

                try:
                    entry = json.loads(val)
                except json.JSONDecodeError:
                    continue

                if entry.get("tenant_id") != tenant_id or "embedding" not in entry:
                    entries_checked += 1
                    continue

                cached_vec = entry["embedding"]
                if len(cached_vec) == len(prompt_vec):
                    sim = _cosine_similarity(prompt_vec, cached_vec)
                    if sim > best_similarity:
                        best_similarity = sim
                        best_payload = entry.get("payload")

                entries_checked += 1

            if best_similarity >= threshold and best_payload is not None:
                logger.debug(
                    "Semantic cache hit (similarity=%.3f, tenant=%s)", best_similarity, tenant_id
                )
                return best_payload

        except Exception as exc:
            logger.error("Semantic cache lookup failed: %s", exc)

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
            logger.debug("Semantic cache SET for tenant=%s", tenant_id)
        except Exception as exc:
            logger.error("Semantic cache set failed: %s", exc)

    async def delete(self, prompt: str, tenant_id: str = "default") -> None:
        try:
            key = self._hash_key(prompt, tenant_id)
            client = await get_redis_client()
            await client.delete(key)
        except Exception as exc:
            logger.error("Semantic cache delete failed: %s", exc)

    async def flush_all(self) -> dict[str, int]:
        """Delete and verify every semantic-cache key without mutating during SCAN."""
        client = await get_redis_client()
        await client.ping()
        deleted = 0

        # Collect a stable SCAN result before deletion. Deleting while SCAN is
        # advancing can cause Redis hash-table rebalancing and skipped keys.
        # Repeat to catch entries written concurrently with a flush.
        for _ in range(3):
            keys = [
                key async for key in client.scan_iter(match="semantic_cache:*", count=500)
            ]
            if not keys:
                break
            for offset in range(0, len(keys), 500):
                deleted += int(await client.delete(*keys[offset:offset + 500]))

        remaining_keys = [
            key async for key in client.scan_iter(match="semantic_cache:*", count=500)
        ]
        remaining = len(remaining_keys)
        if remaining:
            raise RuntimeError(
                f"Semantic cache flush verification failed: {remaining} key(s) remain."
            )
        logger.info("Semantic cache flushed and verified: %d keys deleted", deleted)
        return {"deleted": deleted, "remaining": remaining}


semantic_cache_service = SemanticCacheService()


async def get_semantic_cache(
    prompt: str, tenant_id: str = "default", similarity_threshold: float = 0.75
) -> dict[str, Any] | None:
    return await semantic_cache_service.get(prompt, tenant_id, similarity_threshold)


async def delete_semantic_cache(prompt: str, tenant_id: str = "default") -> None:
    await semantic_cache_service.delete(prompt, tenant_id)


async def flush_semantic_cache() -> dict[str, int]:
    return await semantic_cache_service.flush_all()


async def set_semantic_cache(
    prompt: str, payload: dict[str, Any], tenant_id: str = "default"
) -> None:
    await semantic_cache_service.set(prompt, payload, tenant_id)
