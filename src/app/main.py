from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import sys

# Ensure src root is in sys.path for direct uvicorn invocations
_src_root = str(Path(__file__).resolve().parent.parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from db.postgres import PostgresPool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = PostgresPool(settings)
    await pool.connect()
    app.state.db_pool = pool
    try:
        yield
    finally:
        await pool.disconnect()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Enable CORS for Vite dev server and web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Mount built frontend assets if present
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")

