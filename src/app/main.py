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
    pool = PostgresPool(settings)
    await pool.connect()
    await set_shared_pool(pool)
    app.state.db_pool = pool
    logger.info("Application started — DB pool initialized")
    try:
        yield
    finally:
        await close_shared_pool()
        await close_redis_pool()
        logger.info("Application shutdown — connections closed")


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS — restrict to known origins
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


# Simple API key auth middleware
@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # Skip auth for health check and OPTIONS
    if request.url.path in ("/health", "/docs", "/openapi.json") or request.method == "OPTIONS":
        return await call_next(request)

    settings = get_settings()
    # Skip auth if no API key is configured (development mode)
    if not settings.app_api_key:
        return await call_next(request)

    api_key = request.headers.get("X-API-Key", "")
    if api_key != settings.app_api_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


# Simple in-memory rate limiter
_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 30  # requests per minute
_RATE_LIMIT_WINDOW = 60.0  # seconds


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    import time
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []

    # Remove old entries
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )

    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.app_name}


app.include_router(api_router)

# Mount built frontend assets if present
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
