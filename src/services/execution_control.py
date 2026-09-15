"""Execution identity, schema versioning, and lightweight Redis checkpoints."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from db.redis import get_redis_client


def schema_fingerprint(schema: list[dict[str, Any]] | None) -> str:
    if not schema:
        return ""
    canonical = json.dumps(schema, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def request_fingerprint(
    *, tenant_id: str, user_id: str, session_id: str, prompt: str,
) -> str:
    canonical = "\x1f".join((tenant_id, user_id, session_id, " ".join(prompt.split()).lower()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def save_execution_checkpoint(
    request_id: str, payload: dict[str, Any], *, ttl_seconds: int = 3600,
) -> None:
    if not request_id:
        return
    client = await get_redis_client()
    await client.set(
        f"agent_checkpoint:{request_id}", json.dumps(payload, default=str), ex=ttl_seconds,
    )


async def load_execution_checkpoint(request_id: str) -> dict[str, Any] | None:
    if not request_id:
        return None
    client = await get_redis_client()
    raw = await client.get(f"agent_checkpoint:{request_id}")
    return json.loads(raw) if raw else None

