import json
import logging
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

    # 1. Connect DB pool
    pool = PostgresPool(settings)
    await pool.connect()
    await set_shared_pool(pool)
    app.state.db_pool = pool
    logger.info("DB pool initialized")

    # 2. Start MCP client (spawns mcp_server/server.py subprocess)
    await start_mcp_client()

    # 3. Schema bootstrap via MCP tool + agent-side embedding
    try:
        session = await get_mcp_session()

        # 3a. Fetch raw schema from DB via MCP tool
        result = await session.call_tool("get_schema", arguments={})
        raw_text = result.content[0].text if result.content else "[]"
        raw_catalog = json.loads(raw_text)

        if raw_catalog:
            # 3b. Load into agent-side SchemaRAGService in-memory catalog
            schema_rag_service._live_catalog = raw_catalog
            logger.info("Schema bootstrap: discovered %d tables via MCP", len(raw_catalog))

            # 3c. Embed + upsert pgvector (agent-side: Gemini API + DB)
            if settings.gemini_api_key and settings.gemini_embedding_model:
                from db.postgres import get_shared_pool
                db_pool = await get_shared_pool()
                upserted = await sync_schema_catalog(
                    tenant_id="00000000-0000-0000-0000-000000000001",
                    pool=db_pool,
                )
                logger.info("Schema bootstrap: upserted %d embeddings into pgvector", upserted)
            else:
                logger.warning(
                    "Schema embedding skipped — GEMINI_API_KEY or GEMINI_EMBEDDING_MODEL not set"
                )
        else:
            logger.warning("Schema bootstrap: no tables found (DB may be empty)")

    except Exception as exc:
        logger.error("Schema bootstrap failed: %s", exc)

    logger.info("Application started — MCP client + schema index ready")

    try:
        yield
    finally:
        await stop_mcp_client()
        await close_shared_pool()
        await close_redis_pool()
        logger.info("Application shutdown — all connections closed")


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS
_allowed_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
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


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    import time
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW
    ]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded."})
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
