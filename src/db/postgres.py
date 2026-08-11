import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_shared_pool: "PostgresPool | None" = None
_shared_pool_loop: asyncio.AbstractEventLoop | None = None


class PostgresPool:
    """Asyncpg pool manager used by API handlers and services."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._pool: asyncpg.Pool | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._pool is not None and current_loop is not None and self._loop is not current_loop:
            try:
                await self._pool.close()
            except Exception:
                pass
            self._pool = None
            self._loop = None

        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._settings.postgres_dsn,
                min_size=2,
                max_size=20,
                command_timeout=15,
            )
            self._loop = current_loop
        except Exception as exc:
            logger.warning(
                "Could not connect to PostgreSQL at '%s': %s. Operating in offline mode.",
                self._settings.postgres_host,
                exc,
            )
            self._pool = None
            self._loop = None

    async def disconnect(self) -> None:
        if self._pool is None:
            return
        try:
            await self._pool.close()
        except Exception:
            pass
        self._pool = None
        self._loop = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._pool is not None and current_loop is not None and self._loop is not current_loop:
            self._pool = None
            self._loop = None

        if self._pool is None:
            await self.connect()
        if self._pool is None:
            raise RuntimeError("Postgres pool is not initialized. Check database connectivity.")
        async with self._pool.acquire() as conn:
            yield conn


async def get_shared_pool() -> PostgresPool:
    """Return the application-wide singleton PostgresPool with loop-safety."""
    global _shared_pool, _shared_pool_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _shared_pool is not None and current_loop is not None and _shared_pool_loop is not current_loop:
        try:
            await _shared_pool.disconnect()
        except Exception:
            pass
        _shared_pool = None
        _shared_pool_loop = None

    if _shared_pool is None:
        _shared_pool = PostgresPool()
        await _shared_pool.connect()
        _shared_pool_loop = current_loop
    elif _shared_pool._pool is None:
        await _shared_pool.connect()
        _shared_pool_loop = current_loop
    return _shared_pool


async def set_shared_pool(pool: PostgresPool) -> None:
    """Set the shared pool (called from app lifespan)."""
    global _shared_pool, _shared_pool_loop
    _shared_pool = pool
    try:
        _shared_pool_loop = asyncio.get_running_loop()
    except RuntimeError:
        _shared_pool_loop = None


async def close_shared_pool() -> None:
    """Close the shared pool (called from app lifespan shutdown)."""
    global _shared_pool, _shared_pool_loop
    if _shared_pool is not None:
        await _shared_pool.disconnect()
        _shared_pool = None
        _shared_pool_loop = None
