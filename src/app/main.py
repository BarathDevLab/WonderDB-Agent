from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import sys

# Ensure src root is in sys.path for direct uvicorn invocations
_src_root = str(Path(__file__).resolve().parent.parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from fastapi import FastAPI

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
app.include_router(api_router)
