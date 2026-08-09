import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)





async def generate_embedding(text: str, api_key: str | None = None) -> list[float]:
    if not api_key:
        raise ValueError("API key is required to generate embeddings in production.")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.error(f"Failed to generate embedding: {exc}")
        raise ValueError(f"Failed to generate embedding: {exc}")




_PII_COLUMN_NAMES = {"email", "ssn", "social_security", "password", "phone", "credit_card", "tax_id", "salary"}


class SchemaRAGService:
    """Dynamic Schema RAG service with live information_schema discovery and FK graph traversal."""

    def __init__(self) -> None:
        self._live_catalog: list[dict[str, Any]] | None = None
        self._catalog_embeddings: dict[str, list[float]] = {}

    async def _discover_schema_from_db(self, pool: Any, tenant_id: str) -> list[dict[str, Any]]:
        """Dynamically discover table schemas from PostgreSQL information_schema."""
        try:
            async with pool.acquire() as conn:
                # Get all user tables (exclude system tables)
                columns = await conn.fetch("""
                    SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
                           CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN true ELSE false END AS is_pk
                    FROM information_schema.columns c
                    LEFT JOIN information_schema.key_column_usage kcu
                        ON c.table_name = kcu.table_name AND c.column_name = kcu.column_name
                        AND c.table_schema = kcu.table_schema
                    LEFT JOIN information_schema.table_constraints tc
                        ON kcu.constraint_name = tc.constraint_name
                        AND tc.constraint_type = 'PRIMARY KEY'
                        AND tc.table_schema = kcu.table_schema
                    WHERE c.table_schema = 'public'
                      AND c.table_name NOT IN ('schema_catalog', 'tenants')
                    ORDER BY c.table_name, c.ordinal_position;
                """)

                # Get foreign key relationships
                fk_rows = await conn.fetch("""
                    SELECT
                        tc.table_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table,
                        ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu
                        ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema = 'public';
                """)

                # Build FK lookup
                fk_map: dict[str, list[dict[str, str]]] = {}
                for fk in fk_rows:
                    t = fk["table_name"]
                    if t not in fk_map:
                        fk_map[t] = []
                    fk_map[t].append({
                        "column": fk["column_name"],
                        "foreign_table": fk["foreign_table"],
                        "foreign_column": fk["foreign_column"],
                    })

                # Group into table schemas
                tables: dict[str, dict[str, Any]] = {}
                for row in columns:
                    t_name = row["table_name"]
                    if t_name not in tables:
                        tables[t_name] = {
                            "table_name": t_name,
                            "columns": [],
                            "foreign_keys": fk_map.get(t_name, []),
                            "description": f"Table {t_name} in the enterprise database",
                        }
                    col_name = row["column_name"]
                    tables[t_name]["columns"].append({
                        "name": col_name,
                        "type": row["data_type"].upper(),
                        "is_pk": bool(row["is_pk"]),
                        "is_pii": col_name.lower() in _PII_COLUMN_NAMES,
                    })

                catalog = list(tables.values())
                if catalog:
                    self._live_catalog = catalog
                    logger.info("Discovered %d tables from information_schema", len(catalog))
                return catalog
        except Exception as exc:
            logger.warning("Failed to discover schema from DB: %s", exc)
            return []

    def _get_catalog(self) -> list[dict[str, Any]]:
        """Return live catalog if available, otherwise return empty list."""
        if self._live_catalog:
            return self._live_catalog
        return []

    async def _query_live_pgvector(
        self, prompt_embedding: list[float], tenant_id: str, pool: Any
    ) -> list[dict[str, Any]]:
        try:
            async with pool.acquire() as conn:
                query = """
                    SELECT table_name, column_name, data_type, is_pii, description,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM schema_catalog
                    WHERE tenant_id = $2::uuid
                    ORDER BY similarity DESC
                    LIMIT 15;
                """
                records = await conn.fetch(query, str(prompt_embedding), tenant_id)
                catalog = self._get_catalog()
                table_lookup = {t["table_name"]: t for t in catalog}
                tables: dict[str, dict[str, Any]] = {}
                for r in records:
                    t_name = r["table_name"]
                    if t_name not in tables:
                        seed_table = table_lookup.get(t_name, {})
                        tables[t_name] = {
                            "table_name": t_name,
                            "columns": [],
                            "foreign_keys": seed_table.get("foreign_keys", []),
                            "description": r["description"] or seed_table.get("description", ""),
                        }
                    tables[t_name]["columns"].append(
                        {
                            "name": r["column_name"],
                            "type": r["data_type"],
                            "is_pii": r["is_pii"],
                        }
                    )
                return list(tables.values())
        except Exception:
            return []

    def _traverse_foreign_key_graph(
        self, initial_tables: list[dict[str, Any]], catalog: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        table_lookup = {t["table_name"]: t for t in catalog}
        selected = {t["table_name"] for t in initial_tables}
        result = list(initial_tables)

        for _ in range(2):
            for table in list(result):
                t_name = table["table_name"]
                seed_fks = table_lookup.get(t_name, {}).get("foreign_keys", [])
                for fk in seed_fks:
                    target = fk.get("foreign_table")
                    if target and target in table_lookup and target not in selected:
                        result.append(table_lookup[target])
                        selected.add(target)

            for cat_table in catalog:
                t_name = cat_table["table_name"]
                if t_name not in selected:
                    for fk in cat_table.get("foreign_keys", []):
                        if fk.get("foreign_table") in selected:
                            result.append(cat_table)
                            selected.add(t_name)
                            break

        return result

    async def retrieve_schemas(
        self, prompt: str, tenant_id: str, pool: Any = None, api_key: str | None = None
    ) -> list[dict[str, Any]]:
        if pool is None:
            logger.error("Live DB pool is required for schema retrieval in production.")
            return []

        # Try to discover live schema if not cached
        if self._live_catalog is None:
            await self._discover_schema_from_db(pool, tenant_id)

        try:
            prompt_vec = await generate_embedding(prompt, api_key=api_key)
        except Exception:
            return []

        catalog = self._get_catalog()

        # Attempt live pgvector retrieval
        live_results = await self._query_live_pgvector(prompt_vec, tenant_id, pool)
        if live_results:
            return self._traverse_foreign_key_graph(live_results, catalog)

        return []

    async def sync_schema_catalog_to_db(
        self, tenant_id: str, pool: Any, api_key: str | None = None
    ) -> int:
        catalog = self._get_catalog()
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
                        is_pii = col.get("is_pii", False)
                        desc_text = f"Table {t_name} column {c_name} ({c_type}) - {t_desc}"
                        vec = await generate_embedding(desc_text, api_key=api_key)
                        vec_str = "[" + ",".join(str(v) for v in vec) + "]"

                        await conn.execute(
                            """
                            INSERT INTO schema_catalog (
                                tenant_id, table_name, column_name, data_type,
                                is_primary_key, is_pii, description, embedding
                            )
                            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT DO NOTHING;
                            """,
                            tenant_id, t_name, c_name, c_type, is_pk, is_pii, desc_text, vec_str,
                        )
                        await conn.execute(
                            """
                            UPDATE schema_catalog
                            SET embedding = $1, description = $2
                            WHERE tenant_id = $3::uuid AND table_name = $4 AND column_name = $5;
                            """,
                            vec_str, desc_text, tenant_id, t_name, c_name,
                        )
                        count += 1
        except Exception as exc:
            logger.warning("Failed to sync schema catalog embeddings: %s", exc)
        return count


schema_rag_service = SchemaRAGService()


async def retrieve_schema_context(
    prompt: str, tenant_id: str, pool: Any = None
) -> list[dict[str, Any]]:
    from app.config import get_settings
    settings = get_settings()
    return await schema_rag_service.retrieve_schemas(prompt, tenant_id, pool, api_key=settings.openai_api_key)


async def sync_schema_catalog(
    tenant_id: str, pool: Any, api_key: str | None = None
) -> int:
    return await schema_rag_service.sync_schema_catalog_to_db(tenant_id, pool, api_key)
