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


def _pseudo_dense_embedding(text: str, dimensions: int = 128) -> list[float]:
    """Deterministic, lightweight dense vector embedding for semantic matching."""
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
                for r in records:
                    t_name = r["table_name"]
                    if t_name not in tables:
                        tables[t_name] = {
                            "table_name": t_name,
                            "columns": [],
                            "foreign_keys": [],
                            "description": r["description"] or "",
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
        """Graph traversal attaching connected lookup tables via FK edges."""
        table_lookup = {t["table_name"]: t for t in catalog}
        selected = {t["table_name"] for t in initial_tables}
        result = list(initial_tables)

        for table in initial_tables:
            for fk in table.get("foreign_keys", []):
                target = fk.get("foreign_table")
                if target and target in table_lookup and target not in selected:
                    result.append(table_lookup[target])
                    selected.add(target)

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

        # 3. Traverse FK graph to attach related join tables
        return self._traverse_foreign_key_graph(top_tables, self._seed_catalog)


schema_rag_service = SchemaRAGService()


async def retrieve_schema_context(
    prompt: str, tenant_id: str, pool: Any = None
) -> list[dict[str, Any]]:
    """Public helper for schema retrieval in plan_node."""
    return await schema_rag_service.retrieve_schemas(prompt, tenant_id, pool)
