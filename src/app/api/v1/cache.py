import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from services.semantic_cache import flush_semantic_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])


@router.post("/clear")
@router.delete("")
async def clear_cache() -> dict[str, Any]:
    """Flush all semantic query keys and report verified deletion counts."""
    try:
        result = await flush_semantic_cache()
    except Exception as exc:
        logger.exception("Semantic cache flush endpoint failed")
        raise HTTPException(
            status_code=503,
            detail=f"Semantic cache flush failed: {exc}",
        ) from exc
    return {
        "status": "ok",
        "message": "Semantic query cache flushed and verified.",
        **result,
    }
