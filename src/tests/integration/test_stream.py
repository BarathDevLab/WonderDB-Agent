import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_agent_sse_stream_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent/stream?prompt=Show%20monthly%20revenue&tenant_id=t-1")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers.get("x-accel-buffering") == "no"

        content = response.text
        assert "event: status" in content
        assert "event: plan_ready" in content
        assert "event: execution_complete" in content
        assert "event: final_response" in content
        assert "event: complete" in content


@pytest.mark.asyncio
async def test_agent_sse_stream_post_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"prompt": "List recent orders", "tenant_id": "tenant-test"}
        response = await client.post("/api/v1/agent/stream", json=payload)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = response.text
        assert "event: status" in content
        assert "event: complete" in content


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
