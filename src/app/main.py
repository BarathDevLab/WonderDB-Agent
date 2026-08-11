import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import sys

_src_root = str(Path(__file__).resolve().parent.parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from fastapi import FastAPI, Request, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app.api.router import api_router  # noqa: E402
from app.config import get_settings  # noqa: E402
from db.postgres import PostgresPool, set_shared_pool, close_shared_pool  # noqa: E402
from db.redis import close_redis_pool  # noqa: E402
from agent.mcp_client import start_mcp_client, stop_mcp_client, get_mcp_session  # noqa: E402
from services.schema_rag import schema_rag_service, sync_schema_catalog  # noqa: E402

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # ── 1. Connect Postgres pool ─────────────────────────────────────────
    pool = PostgresPool(settings)
    await pool.connect()
    await set_shared_pool(pool)
    app.state.db_pool = pool
    logger.info("DB pool initialized")

    # ── 2. Start MCP subprocess ──────────────────────────────────────────
    try:
        await start_mcp_client()
    except Exception as exc:
        # Non-fatal: MCP unavailable degrades gracefully (nodes handle None session)
        logger.error("MCP client failed to start (non-fatal): %s", exc)

    # ── 3. Schema bootstrap ──────────────────────────────────────────────
    try:
        session = await get_mcp_session()

        result = await session.call_tool("get_schema", arguments={})
        raw_text = result.content[0].text if result.content else "[]"
        raw_catalog = json.loads(raw_text)

        if raw_catalog:
            schema_rag_service._live_catalog = raw_catalog
            logger.info("Schema bootstrap: discovered %d tables via MCP", len(raw_catalog))

            if settings.gemini_api_key and settings.gemini_embedding_model:
                from db.postgres import get_shared_pool
                db_pool = await get_shared_pool()
                upserted = await sync_schema_catalog(
                    tenant_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                    pool=db_pool,
                )
                logger.info("Schema bootstrap: upserted %d embeddings into pgvector", upserted)
            else:
                logger.warning(
                    "Schema embedding skipped — GEMINI_API_KEY or GEMINI_EMBEDDING_MODEL not set"
                )
        else:
            logger.warning("Schema bootstrap: no tables found (DB may be empty)")

    except RuntimeError:
        # MCP session not available — schema bootstrap skipped gracefully
        logger.warning("Schema bootstrap skipped — MCP session not available")
    except Exception as exc:
        logger.error("Schema bootstrap failed (non-fatal): %s", exc)

    logger.info("Application started — ready to serve requests")

    try:
        yield
    finally:
        # ── Shutdown sequence ────────────────────────────────────────────
        # Each step is individually guarded so one failure doesn't block others.
        # CancelledError and KeyboardInterrupt are EXPECTED during Ctrl+C shutdown
        # (Uvicorn cancels the asyncio task) — suppress them to avoid noisy tracebacks.
        import asyncio

        async def _safe_shutdown(coro, label: str) -> None:
            try:
                await coro
            except (asyncio.CancelledError, KeyboardInterrupt):
                # Normal during Ctrl+C / SIGTERM — not an error
                pass
            except Exception as exc:
                logger.warning("Shutdown step '%s' raised: %s", label, exc)

        await _safe_shutdown(stop_mcp_client(), "stop_mcp_client")
        await _safe_shutdown(close_shared_pool(), "close_shared_pool")
        await _safe_shutdown(close_redis_pool(), "close_redis_pool")
        logger.info("Application shutdown complete")


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS — restrict origins in production via CORS_ORIGINS env var
import os as _os
_cors_origins_env = _os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json") or request.method == "OPTIONS":
        return await call_next(request)
    settings = get_settings()
    if not settings.app_api_key:
        return await call_next(request)
    api_key = request.headers.get("X-API-Key", "")
    if api_key != settings.app_api_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 30
_RATE_LIMIT_WINDOW = 60.0
# Cleanup threshold: evict IPs with no recent activity to prevent memory leak
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # seconds between full cleanups
_rate_limit_last_cleanup: float = 0.0


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    import time
    if request.url.path in ("/health", "/docs", "/openapi.json") or request.method == "OPTIONS":
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Bug fix: periodically evict stale IPs to prevent unbounded dict growth.
    # Without this, the dict accumulates every unique IP seen since startup.
    global _rate_limit_last_cleanup
    if now - _rate_limit_last_cleanup > _RATE_LIMIT_CLEANUP_INTERVAL:
        stale = [ip for ip, ts in _rate_limit_store.items() if not any(now - t < _RATE_LIMIT_WINDOW for t in ts)]
        for ip in stale:
            del _rate_limit_store[ip]
        _rate_limit_last_cleanup = now

    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW
    ]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again shortly."})
    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.app_name}


app.include_router(api_router)

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
