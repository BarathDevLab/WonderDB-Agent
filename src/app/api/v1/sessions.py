from typing import Any
from fastapi import APIRouter, Query
from services.session_memory import session_memory_service


router = APIRouter(tags=["sessions"])


@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Retrieve chronological event history for an active session."""
    events = await session_memory_service.get_session_history(session_id, limit=limit)
    return {
        "session_id": session_id,
        "count": len(events),
        "events": events,
    }


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """List session metadata."""
    return {"status": "active", "storage": "redis_backed_with_fallback"}
