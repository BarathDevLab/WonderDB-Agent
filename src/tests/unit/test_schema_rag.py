import pytest
from services.schema_rag import (
    SchemaRAGService,
)
from services.semantic_cache import _cosine_similarity

@pytest.mark.asyncio
async def test_embedding_generation_1536_dimensions():
    """Verify the semantic cache embedding function returns correct dimensionality."""
    from services.semantic_cache import _get_neural_embedding
    text = "Show all customers and orders with total spending"
    emb = await _get_neural_embedding(text)
    assert len(emb) == 1536
    assert isinstance(emb[0], float)

@pytest.mark.asyncio
async def test_schema_rag_semantic_matching():
    rag = SchemaRAGService()
    # Prompt about products and sales
    schemas = await rag.retrieve_schemas("Find high value products and inventory SKUs", "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    table_names = [s["table_name"] for s in schemas]
    assert "products" in table_names

@pytest.mark.asyncio
async def test_schema_rag_foreign_key_graph_traversal():
    rag = SchemaRAGService()
    # Orders should pull connected customers via FK traversal
    schemas = await rag.retrieve_schemas("Show recent customer orders and billing totals", "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    table_names = [s["table_name"] for s in schemas]
    assert "orders" in table_names
    assert "customers" in table_names

def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert pytest.approx(_cosine_similarity(v1, v2), 0.01) == 1.0
    assert pytest.approx(_cosine_similarity(v1, v3), 0.01) == 0.0
