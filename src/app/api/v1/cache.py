from fastapi import APIRouter
from services.semantic_cache import flush_semantic_cache

router = APIRouter(prefix="/cache", tags=["cache"])


@router.post("/clear")
@router.delete("")
async def clear_cache() -> dict[str, str]:
    """Flush all cached queries from Redis and memory."""
    await flush_semantic_cache()
    return {"status": "ok", "message": "Semantic query cache flushed successfully."}
