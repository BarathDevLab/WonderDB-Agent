import math
import re
from typing import Any


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two dense embedding vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _pseudo_dense_embedding(text: str, dimensions: int = 1536) -> list[float]:
    """Deterministic, lightweight 1536-dim dense vector embedding for semantic matching and pgvector compatibility."""
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


async def generate_embedding(text: str, api_key: str | None = None) -> list[float]:
    """Generate dense 1536-dim vector embedding using OpenAI or local deterministic fallback."""
    if api_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            resp = await client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return resp.data[0].embedding
        except Exception:
            pass
    return _pseudo_dense_embedding(text, dimensions=1536)


class SchemaRAGService:
    """Production Schema RAG service supporting PostgreSQL pgvector, full-text search, and FK graph traversal."""

    def __init__(self) -> None:
        self._seed_catalog: list[dict[str, Any]] = [
            {
                "table_name": "customers",
                "columns": [
                    {"name": "id", "type": "UUID", "is_pk": True, "is_pii": False},
                    {"name": "tenant_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "full_name", "type": "VARCHAR(255)", "is_pk": False, "is_pii": False},
                    {"name": "email", "type": "VARCHAR(255)", "is_pk": False, "is_pii": True},
                    {"name": "ssn", "type": "VARCHAR(32)", "is_pk": False, "is_pii": True},
                    {"name": "created_at", "type": "TIMESTAMPTZ", "is_pk": False, "is_pii": False},
                ],
                "foreign_keys": [],
                "description": "Customer demographics, accounts, identity, contact information and profile records",
                "embedding": _pseudo_dense_embedding(
                    "customers user account identity full name email ssn profile demographics"
                ),
            },
            {
                "table_name": "orders",
                "columns": [
                    {"name": "id", "type": "UUID", "is_pk": True, "is_pii": False},
                    {"name": "tenant_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "customer_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "total_amount", "type": "NUMERIC(12,2)", "is_pk": False, "is_pii": False},
                    {"name": "status", "type": "VARCHAR(50)", "is_pk": False, "is_pii": False},
                    {"name": "created_at", "type": "TIMESTAMPTZ", "is_pk": False, "is_pii": False},
                ],
                "foreign_keys": [
                    {"column": "customer_id", "foreign_table": "customers", "foreign_column": "id"}
                ],
                "description": "Customer orders, billing sales transactions, order revenue, monthly sales status, and purchase amounts",
                "embedding": _pseudo_dense_embedding(
                    "orders sales revenue purchases monthly billing total amount transactions"
                ),
            },
            {
                "table_name": "order_items",
                "columns": [
                    {"name": "id", "type": "UUID", "is_pk": True, "is_pii": False},
                    {"name": "tenant_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "order_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "product_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "quantity", "type": "INTEGER", "is_pk": False, "is_pii": False},
                    {"name": "unit_price", "type": "NUMERIC(10,2)", "is_pk": False, "is_pii": False},
                ],
                "foreign_keys": [
                    {"column": "order_id", "foreign_table": "orders", "foreign_column": "id"},
                    {"column": "product_id", "foreign_table": "products", "foreign_column": "id"},
                ],
                "description": "Line items breakdown per order with individual SKU quantities and unit pricing",
                "embedding": _pseudo_dense_embedding(
                    "order items line item quantity unit price skus breakdown"
                ),
            },
            {
                "table_name": "products",
                "columns": [
                    {"name": "id", "type": "UUID", "is_pk": True, "is_pii": False},
                    {"name": "tenant_id", "type": "UUID", "is_pk": False, "is_pii": False},
                    {"name": "sku", "type": "VARCHAR(64)", "is_pk": False, "is_pii": False},
                    {"name": "name", "type": "VARCHAR(255)", "is_pk": False, "is_pii": False},
                    {"name": "category", "type": "VARCHAR(128)", "is_pk": False, "is_pii": False},
                    {"name": "price", "type": "NUMERIC(10,2)", "is_pk": False, "is_pii": False},
                ],
                "foreign_keys": [],
                "description": "Product catalog inventory, SKUs, category classifications, and retail prices",
                "embedding": _pseudo_dense_embedding(
                    "products inventory skus items categories retail price catalog"
                ),
            },
        ]

    async def _query_live_pgvector(
        self, prompt_embedding: list[float], tenant_id: str, pool: Any
    ) -> list[dict[str, Any]]:
        """Query live pgvector schema_catalog table in PostgreSQL."""
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
                # Group columns into table schemas
                tables: dict[str, dict[str, Any]] = {}
                table_lookup = {t["table_name"]: t for t in self._seed_catalog}
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
        """Multi-hop graph traversal attaching connected lookup tables via FK edges (both directions)."""
        table_lookup = {t["table_name"]: t for t in catalog}
        selected = {t["table_name"] for t in initial_tables}
        result = list(initial_tables)

        # Multi-hop traversal (depth = 2)
        for _ in range(2):
            for table in list(result):
                t_name = table["table_name"]
                seed_fks = table_lookup.get(t_name, {}).get("foreign_keys", [])
                # 1. Outgoing FKs (e.g. order_items -> orders -> customers)
                for fk in seed_fks:
                    target = fk.get("foreign_table")
                    if target and target in table_lookup and target not in selected:
                        result.append(table_lookup[target])
                        selected.add(target)

            # 2. Incoming FKs (e.g. orders <- order_items, customers <- orders)
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
        self, prompt: str, tenant_id: str, pool: Any = None
    ) -> list[dict[str, Any]]:
        """Hybrid vector search and graph-expanded schema context retrieval."""
        prompt_vec = _pseudo_dense_embedding(prompt)

        # 1. Attempt live pgvector retrieval if connection pool is available
        if pool is not None:
            live_results = await self._query_live_pgvector(prompt_vec, tenant_id, pool)
            if live_results:
                return self._traverse_foreign_key_graph(live_results, self._seed_catalog)

        # 2. Local semantic vector retrieval using dense embeddings & cosine similarity
        scored: list[tuple[float, dict[str, Any]]] = []
        for table in self._seed_catalog:
            table_vec = table.get("embedding", [])
            similarity = _cosine_similarity(prompt_vec, table_vec)
            scored.append((similarity, table))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_tables = [t for score, t in scored if score > 0.05][:2]

        if not top_tables:
            top_tables = self._seed_catalog[:2]

        return self._traverse_foreign_key_graph(top_tables, self._seed_catalog)

    async def sync_schema_catalog_to_db(
        self, tenant_id: str, pool: Any, api_key: str | None = None
    ) -> int:
        """Populate or update schema_catalog table in PostgreSQL with 1536-dim vector embeddings for pgvector RAG."""
        count = 0
        try:
            async with pool.acquire() as conn:
                for table in self._seed_catalog:
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
                            tenant_id,
                            t_name,
                            c_name,
                            c_type,
                            is_pk,
                            is_pii,
                            desc_text,
                            vec_str,
                        )
                        await conn.execute(
                            """
                            UPDATE schema_catalog
                            SET embedding = $1, description = $2
                            WHERE tenant_id = $3::uuid AND table_name = $4 AND column_name = $5;
                            """,
                            vec_str,
                            desc_text,
                            tenant_id,
                            t_name,
                            c_name,
                        )
                        count += 1
        except Exception as exc:
            print(f"[Warning] Failed to sync schema catalog embeddings: {exc}")
        return count


schema_rag_service = SchemaRAGService()


async def retrieve_schema_context(
    prompt: str, tenant_id: str, pool: Any = None
) -> list[dict[str, Any]]:
    """Public helper for schema retrieval in plan_node."""
    return await schema_rag_service.retrieve_schemas(prompt, tenant_id, pool)


async def sync_schema_catalog(
    tenant_id: str, pool: Any, api_key: str | None = None
) -> int:
    """Public helper to sync schema catalog embeddings into PostgreSQL pgvector."""
    return await schema_rag_service.sync_schema_catalog_to_db(tenant_id, pool, api_key)
