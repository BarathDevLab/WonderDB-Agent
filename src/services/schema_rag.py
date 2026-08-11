"""
Schema RAG Service
==================
Purpose
-------
Retrieval-Augmented Generation (RAG) over the **database schema itself** so
that an AI agent can answer arbitrary natural-language queries without ever
being hard-coded to a specific table layout.

Three-phase lifecycle
---------------------
PHASE 1 – FETCH (discover)
    Read every table / column / FK from PostgreSQL ``information_schema`` at
    runtime.  The result is cached in memory as ``_live_catalog``.

PHASE 2 – EMBED & STORE (index)
    For each column in the live catalog, generate a Gemini vector embedding of
    a human-readable description ("Table orders column total_amount …") and
    upsert it into the ``schema_catalog`` pgvector table so it survives
    restarts and is shared across replicas.

PHASE 3 – VECTOR SEARCH (retrieve)
    When the agent receives a user prompt, embed the prompt with the same
    Gemini model, run a cosine-distance ANN query against ``schema_catalog``
    (pgvector ``<=>`` operator), and expand the hit-set by traversing FK edges
    in both directions (2 hops).  The returned list of table/column dicts is
    injected into the LLM prompt as grounded schema context.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PII_COLUMN_NAMES: frozenset[str] = frozenset(
    {"email", "ssn", "social_security", "password", "phone", "credit_card", "tax_id", "salary"}
)

# Columns excluded from information_schema discovery (internal / system tables)
_EXCLUDED_TABLES: frozenset[str] = frozenset({"schema_catalog", "tenants"})

# Number of top-k columns returned from the vector search before FK expansion
_VECTOR_TOP_K: int = 15

# FK graph traversal depth (2 = include direct FKs and their FKs)
_FK_HOPS: int = 2

# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

_shared_httpx: httpx.AsyncClient | None = None


def _get_httpx_client() -> httpx.AsyncClient:
    """Return (or lazily create) a shared async HTTP client."""
    global _shared_httpx
    if _shared_httpx is None or _shared_httpx.is_closed:
        _shared_httpx = httpx.AsyncClient(timeout=15.0)
    return _shared_httpx


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def generate_embedding(text: str, api_key: str, model: str) -> list[float]:
    """
    Generate a text embedding vector via the Gemini Embedding API.

    Args:
        text:    The text to embed.
        api_key: Gemini API key.
        model:   Gemini embedding model name (e.g. ``text-embedding-004``).

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        ValueError: If the API returns a non-200 response.
    """
    clean_model = model.strip()
    if clean_model.startswith("models/"):
        clean_model = clean_model[len("models/"):]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}"
        f":embedContent?key={api_key}"
    )
    payload = {
        "model": f"models/{clean_model}",
        "content": {"parts": [{"text": text}]},
    }
    client = _get_httpx_client()
    
    max_retries = 5
    base_delay = 1.0

    for attempt in range(max_retries):
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            return resp.json()["embedding"]["values"]
        
        if resp.status_code == 429:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Gemini API rate limited (429). Retrying in %.2fs (attempt %d/%d)",
                    delay, attempt + 1, max_retries
                )
                await asyncio.sleep(delay)
                continue

        raise ValueError(
            f"Gemini embedding API returned {resp.status_code}: {resp.text[:200]}"
        )
    
    raise ValueError(f"Failed to generate embedding after {max_retries} attempts.")


def _vec_to_pgvector(vec: list[float]) -> str:
    """Serialize a Python float list to the pgvector literal ``[v1,v2,…]``."""
    return "[" + ",".join(str(v) for v in vec) + "]"


# ---------------------------------------------------------------------------
# SchemaRAGService
# ---------------------------------------------------------------------------


class SchemaRAGService:
    """
    Three-phase Schema RAG engine.

    * **Phase 1 – Fetch**: ``_discover_schema_from_db``
    * **Phase 2 – Embed & Store**: ``sync_schema_catalog_to_db``
    * **Phase 3 – Vector Search**: ``retrieve_schemas``
    """

    def __init__(self) -> None:
        # In-memory cache of the live catalog (populated in Phase 1).
        self._live_catalog: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # PHASE 1 – FETCH
    # ------------------------------------------------------------------

    async def _discover_schema_from_db(self, pool: Any) -> list[dict[str, Any]]:
        """
        Phase 1: Query ``information_schema`` to fetch all user tables,
        columns, PK flags, and FK relationships.

        Populates ``self._live_catalog`` and returns the catalog list.
        Result is cached for the lifetime of the process; call
        ``refresh_catalog`` to force a reload.
        """
        try:
            async with pool.acquire() as conn:

                # ── Columns + PK flag ──────────────────────────────────────
                column_rows = await conn.fetch("""
                    SELECT
                        c.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        CASE WHEN tc.constraint_type = 'PRIMARY KEY'
                             THEN true ELSE false END AS is_pk
                    FROM information_schema.columns c
                    LEFT JOIN information_schema.key_column_usage kcu
                        ON  c.table_name   = kcu.table_name
                        AND c.column_name  = kcu.column_name
                        AND c.table_schema = kcu.table_schema
                    LEFT JOIN information_schema.table_constraints tc
                        ON  kcu.constraint_name = tc.constraint_name
                        AND tc.constraint_type  = 'PRIMARY KEY'
                        AND tc.table_schema     = kcu.table_schema
                    WHERE c.table_schema = 'public'
                      AND c.table_name NOT IN ('schema_catalog', 'tenants')
                    ORDER BY c.table_name, c.ordinal_position;
                """)

                # ── Foreign-key relationships ──────────────────────────────
                fk_rows = await conn.fetch("""
                    SELECT
                        tc.table_name,
                        kcu.column_name,
                        ccu.table_name  AS foreign_table,
                        ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON  tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema    = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu
                        ON  tc.constraint_name = ccu.constraint_name
                        AND tc.table_schema    = ccu.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema    = 'public';
                """)

            # Build FK lookup: table_name → list of FK dicts
            fk_map: dict[str, list[dict[str, str]]] = {}
            for fk in fk_rows:
                fk_map.setdefault(fk["table_name"], []).append({
                    "column": fk["column_name"],
                    "foreign_table": fk["foreign_table"],
                    "foreign_column": fk["foreign_column"],
                })

            # Group columns into per-table catalog entries
            tables: dict[str, dict[str, Any]] = {}
            for row in column_rows:
                t_name = row["table_name"]
                if t_name not in tables:
                    tables[t_name] = {
                        "table_name": t_name,
                        "columns": [],
                        "foreign_keys": fk_map.get(t_name, []),
                        "description": f"Table {t_name} in the enterprise database",
                    }
                col_name = row["column_name"]
                # Determine FK membership from the FK map
                col_fk = next(
                    (fk for fk in fk_map.get(t_name, []) if fk["column"] == col_name),
                    None,
                )
                tables[t_name]["columns"].append({
                    "name": col_name,
                    "type": row["data_type"].upper(),
                    "is_pk": bool(row["is_pk"]),
                    "is_fk": col_fk is not None,
                    "foreign_table": col_fk["foreign_table"] if col_fk else None,
                    "foreign_column": col_fk["foreign_column"] if col_fk else None,
                    "is_pii": col_name.lower() in _PII_COLUMN_NAMES,
                })

            catalog = list(tables.values())
            if catalog:
                self._live_catalog = catalog
                logger.info(
                    "Phase 1 – Discovered %d tables from information_schema", len(catalog)
                )
            else:
                logger.warning("Phase 1 – No user tables found in public schema")
            return catalog

        except Exception as exc:
            logger.error("Phase 1 – Failed to discover schema from DB: %s", exc)
            return []

    async def refresh_catalog(self, pool: Any) -> list[dict[str, Any]]:
        """Force a fresh discovery, bypassing the in-memory cache."""
        self._live_catalog = None
        return await self._discover_schema_from_db(pool)

    def _get_catalog(self) -> list[dict[str, Any]]:
        return self._live_catalog or []

    # ------------------------------------------------------------------
    # PHASE 2 – EMBED & STORE
    # ------------------------------------------------------------------

    async def sync_schema_catalog_to_db(
        self, tenant_id: str, pool: Any, api_key: str, model: str
    ) -> int:
        """
        Phase 2: Embed every column description and upsert into
        ``schema_catalog`` (pgvector).

        This method should be called once after DB initialization (or
        whenever the schema changes) to populate / refresh the vector index.

        Returns:
            Number of rows upserted.
        """
        catalog = self._get_catalog()
        if not catalog:
            logger.warning(
                "Phase 2 – Live catalog is empty; run _discover_schema_from_db first"
            )
            return 0

        count = 0
        try:
            async with pool.acquire() as conn:
                for table in catalog:
                    t_name = table["table_name"]
                    t_desc = table.get("description", "")

                    for col in table.get("columns", []):
                        c_name = col["name"]
                        c_type = col["type"]
                        is_pk = col.get("is_pk", False)
                        is_fk = col.get("is_fk", False)
                        is_pii = col.get("is_pii", False)
                        fk_table = col.get("foreign_table")
                        fk_col = col.get("foreign_column")

                        # Human-readable description used as the embedding text
                        desc_text = (
                            f"Table {t_name} column {c_name} ({c_type}) – {t_desc}"
                        )
                        if is_fk and fk_table:
                            desc_text += f". References {fk_table}.{fk_col}"

                        # Generate embedding via Gemini
                        vec = await generate_embedding(desc_text, api_key=api_key, model=model)
                        vec_str = _vec_to_pgvector(vec)

                        # Upsert – requires UNIQUE(tenant_id, table_name, column_name)
                        await conn.execute(
                            """
                            INSERT INTO schema_catalog (
                                tenant_id, table_name, column_name, data_type,
                                is_primary_key, is_foreign_key, foreign_table, foreign_column,
                                is_pii, description, embedding
                            )
                            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                            ON CONFLICT (tenant_id, table_name, column_name)
                            DO UPDATE SET
                                data_type      = EXCLUDED.data_type,
                                is_primary_key = EXCLUDED.is_primary_key,
                                is_foreign_key = EXCLUDED.is_foreign_key,
                                foreign_table  = EXCLUDED.foreign_table,
                                foreign_column = EXCLUDED.foreign_column,
                                is_pii         = EXCLUDED.is_pii,
                                description    = EXCLUDED.description,
                                embedding      = EXCLUDED.embedding;
                            """,
                            tenant_id, t_name, c_name, c_type,
                            is_pk, is_fk, fk_table, fk_col,
                            is_pii, desc_text, vec_str,
                        )
                        count += 1
                        
                        # Rate limit the batch to avoid immediate 429s on free tier
                        await asyncio.sleep(2.0)

            logger.info(
                "Phase 2 – Upserted %d schema embeddings for tenant %s", count, tenant_id
            )
        except Exception as exc:
            logger.error(
                "Phase 2 – Failed to sync schema catalog embeddings: %s", exc
            )
        return count

    # ------------------------------------------------------------------
    # PHASE 3 – VECTOR SEARCH
    # ------------------------------------------------------------------

    async def _vector_search(
        self, prompt_embedding: list[float], tenant_id: str, pool: Any
    ) -> list[dict[str, Any]]:
        """
        Phase 3a: Run a cosine-distance ANN query against ``schema_catalog``
        using the pgvector ``<=>`` operator.

        Returns a list of table dicts (columns filtered to top-k hits).
        """
        try:
            vec_str = _vec_to_pgvector(prompt_embedding)
            async with pool.acquire() as conn:
                records = await conn.fetch(
                    """
                    SELECT
                        table_name, column_name, data_type,
                        is_foreign_key, foreign_table, foreign_column,
                        is_pii, description,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM schema_catalog
                    WHERE tenant_id = $2::uuid
                    ORDER BY similarity DESC
                    LIMIT $3;
                    """,
                    vec_str,
                    tenant_id,
                    _VECTOR_TOP_K,
                )

            # Merge column-level hits back into table-level dicts
            table_lookup = {t["table_name"]: t for t in self._get_catalog()}
            tables: dict[str, dict[str, Any]] = {}
            for r in records:
                t_name = r["table_name"]
                if t_name not in tables:
                    seed = table_lookup.get(t_name, {})
                    tables[t_name] = {
                        "table_name": t_name,
                        "columns": [],
                        "foreign_keys": seed.get("foreign_keys", []),
                        "description": r["description"] or seed.get("description", ""),
                    }
                tables[t_name]["columns"].append({
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "is_fk": r["is_foreign_key"],
                    "foreign_table": r["foreign_table"],
                    "foreign_column": r["foreign_column"],
                    "is_pii": r["is_pii"],
                    "similarity": float(r["similarity"]),
                })

            result = list(tables.values())
            logger.debug(
                "Phase 3 – Vector search returned %d tables for tenant %s",
                len(result),
                tenant_id,
            )
            return result

        except Exception as exc:
            logger.error("Phase 3 – pgvector search failed: %s", exc)
            return []

    def _expand_via_fk_graph(
        self,
        seed_tables: list[dict[str, Any]],
        catalog: list[dict[str, Any]],
        hops: int = _FK_HOPS,
    ) -> list[dict[str, Any]]:
        """
        Phase 3b: Expand the seed set by traversing FK edges in both directions.

        Outbound: seed table → referenced tables (follow FK).
        Inbound:  tables in catalog that reference any already-selected table.

        Args:
            seed_tables: Tables returned by the vector search.
            catalog:     Full live catalog for FK resolution.
            hops:        Number of expansion rounds (default ``_FK_HOPS = 2``).

        Returns:
            Expanded list of table dicts (seed + FK-connected neighbours).
        """
        table_lookup = {t["table_name"]: t for t in catalog}
        selected: set[str] = {t["table_name"] for t in seed_tables}
        result: list[dict[str, Any]] = list(seed_tables)

        for _ in range(hops):
            # Outbound: follow FKs from already-selected tables
            for table in list(result):
                for fk in table_lookup.get(table["table_name"], {}).get("foreign_keys", []):
                    target = fk.get("foreign_table")
                    if target and target in table_lookup and target not in selected:
                        result.append(table_lookup[target])
                        selected.add(target)

            # Inbound: find catalog tables whose FKs point at a selected table
            for cat_table in catalog:
                t_name = cat_table["table_name"]
                if t_name not in selected:
                    if any(
                        fk.get("foreign_table") in selected
                        for fk in cat_table.get("foreign_keys", [])
                    ):
                        result.append(cat_table)
                        selected.add(t_name)

        return result

    async def retrieve_schemas(
        self,
        prompt: str,
        tenant_id: str,
        pool: Any,
        api_key: str,
        model: str,
    ) -> list[dict[str, Any]]:
        """
        Full Phase 3 pipeline: embed prompt → vector search → FK expansion.

        Args:
            prompt:    The natural-language user query.
            tenant_id: Tenant UUID (RLS isolation).
            pool:      Active asyncpg connection pool.
            api_key:   Gemini API key.
            model:     Gemini embedding model name.

        Returns:
            Ordered list of relevant table/column dicts for LLM context.
        """
        # Ensure Phase 1 has run
        if self._live_catalog is None:
            await self._discover_schema_from_db(pool)

        # Embed the user prompt
        try:
            prompt_vec = await generate_embedding(prompt, api_key=api_key, model=model)
        except Exception as exc:
            logger.error(
                "Phase 3 – Failed to embed user prompt for schema retrieval: %s", exc
            )
            return []

        # Vector search (Phase 3a)
        hits = await self._vector_search(prompt_vec, tenant_id, pool)
        if not hits:
            logger.warning(
                "Phase 3 – No schema matches found for tenant %s; "
                "ensure sync_schema_catalog_to_db has been run",
                tenant_id,
            )
            return []

        # FK graph expansion (Phase 3b)
        return self._expand_via_fk_graph(hits, self._get_catalog())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

schema_rag_service = SchemaRAGService()


# ---------------------------------------------------------------------------
# Public API (used by agent nodes and scripts)
# ---------------------------------------------------------------------------


async def retrieve_schema_context(
    prompt: str, tenant_id: str, pool: Any
) -> list[dict[str, Any]]:
    """
    Phase 3 entry point used by the planning agent node.

    Reads ``gemini_api_key`` and ``gemini_embedding_model`` from settings.
    """
    settings = get_settings()
    return await schema_rag_service.retrieve_schemas(
        prompt=prompt,
        tenant_id=tenant_id,
        pool=pool,
        api_key=settings.gemini_api_key,
        model=settings.gemini_embedding_model,
    )


async def sync_schema_catalog(
    tenant_id: str,
    pool: Any,
    api_key: str | None = None,
    model: str | None = None,
) -> int:
    """
    Phase 1 + Phase 2 entry point used by the DB initialisation script.

    Discovers the live schema first (Phase 1) then embeds and stores it
    (Phase 2).  Pass ``api_key`` / ``model`` overrides to bypass settings.
    """
    settings = get_settings()
    resolved_key = api_key or settings.gemini_api_key
    resolved_model = model or settings.gemini_embedding_model

    # Phase 1 – always refresh before indexing
    await schema_rag_service.refresh_catalog(pool)

    # Phase 2 – embed & upsert
    return await schema_rag_service.sync_schema_catalog_to_db(
        tenant_id=tenant_id,
        pool=pool,
        api_key=resolved_key,
        model=resolved_model,
    )
