from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.graph import get_graph
from agent.sse import run_langgraph_sse
from agent.state import GlobalState
from core.sse_formatter import format_sse_event


router = APIRouter(tags=["agent"])


class ChatStreamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    tenant_id: str = Field(default="default-tenant", max_length=64, description="Active tenant UUID")
    user_id: str = Field(default="anonymous", max_length=128, description="Authenticated user ID")
    session_id: str | None = Field(default=None, max_length=128, description="Optional session conversation ID")


async def _generate_sse_stream(initial_state: GlobalState) -> AsyncIterator[str]:
    try:
        graph = get_graph()
        async for event in run_langgraph_sse(graph, initial_state):
            yield event
    except Exception as exc:
        payload: dict[str, Any] = {"message": str(exc)}
        yield format_sse_event("error", payload)


@router.get("/agent/stream")
async def stream_agent_get(
    prompt: str = Query(..., min_length=1, max_length=2000),
    tenant_id: str = Query(default="default-tenant", max_length=64),
    user_id: str = Query(default="anonymous"),
    session_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream live LangGraph Text-to-SQL state transitions over HTTP/2 SSE."""
    sid = session_id or f"session-{tenant_id}"
    initial_state: GlobalState = {
        "prompt": prompt,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": sid,
        "retry_count": 0,
    }
    return StreamingResponse(
        _generate_sse_stream(initial_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/stream")
async def stream_agent_post(request: ChatStreamRequest) -> StreamingResponse:
    """POST variant for streaming with complex query payloads."""
    sid = request.session_id or f"session-{request.tenant_id}"
    initial_state: GlobalState = {
        "prompt": request.prompt,
        "tenant_id": request.tenant_id,
        "user_id": request.user_id,
        "session_id": sid,
        "retry_count": 0,
    }
    return StreamingResponse(
        _generate_sse_stream(initial_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
