import pytest

import services.schema_rag as schema_rag_module
from services.schema_rag import SchemaRAGService
from services.semantic_cache import _cosine_similarity


CATALOG = [
    {
        "table_name": "customers",
        "columns": [{"name": "customer_id", "type": "INTEGER", "is_pk": True}],
        "foreign_keys": [],
    },
    {
        "table_name": "orders",
        "columns": [{"name": "customer_id", "type": "INTEGER", "is_fk": True}],
        "foreign_keys": [{
            "column": "customer_id",
            "foreign_table": "customers",
            "foreign_column": "customer_id",
        }],
    },
]


def test_schema_rag_foreign_key_graph_traversal() -> None:
    rag = SchemaRAGService()

    schemas = rag._expand_via_fk_graph([CATALOG[1]], CATALOG)

    assert [schema["table_name"] for schema in schemas] == ["orders", "customers"]


@pytest.mark.asyncio
async def test_schema_rag_falls_back_to_live_catalog_when_embedding_fails(
    monkeypatch,
) -> None:
    rag = SchemaRAGService()
    rag._live_catalog = CATALOG

    async def failed_embedding(*_args, **_kwargs):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(schema_rag_module, "generate_embedding", failed_embedding)

    schemas = await rag.retrieve_schemas(
        "show the database schema",
        "tenant-a",
        pool=object(),
        api_key="unused",
        model="unused",
    )

    assert schemas == CATALOG


@pytest.mark.asyncio
async def test_schema_diagram_can_bypass_vector_search(monkeypatch) -> None:
    rag = SchemaRAGService()
    rag._live_catalog = CATALOG

    async def unexpected_embedding(*_args, **_kwargs):
        raise AssertionError("full-catalog diagram retrieval must not call embeddings")

    monkeypatch.setattr(schema_rag_module, "generate_embedding", unexpected_embedding)

    schemas = await rag.retrieve_schemas(
        "show the actual schema and process flow",
        "tenant-a",
        pool=object(),
        api_key="unused",
        model="unused",
        prefer_full_catalog=True,
    )

    assert schemas == CATALOG


def test_cosine_similarity() -> None:
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert pytest.approx(_cosine_similarity(v1, v2), 0.01) == 1.0
    assert pytest.approx(_cosine_similarity(v1, v3), 0.01) == 0.0
