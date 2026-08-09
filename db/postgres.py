import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_shared_pool: "PostgresPool | None" = None


class PostgresPool:
    """Asyncpg pool manager used by API handlers and services."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._settings.postgres_dsn,
                min_size=2,
                max_size=20,
                command_timeout=15,
            )
        except Exception as exc:
            logger.warning("Could not connect to PostgreSQL: %s. Operating in offline mode.", exc)
            self._pool = None

    async def disconnect(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        if self._pool is None:
            await self.connect()
        if self._pool is None:
            raise RuntimeError("Postgres pool is not initialized. Check database connectivity.")
        async with self._pool.acquire() as conn:
            yield conn


async def get_shared_pool() -> PostgresPool:
    """Return the application-wide singleton PostgresPool."""
    global _shared_pool
    if _shared_pool is None:
        _shared_pool = PostgresPool()
        await _shared_pool.connect()
    return _shared_pool


async def set_shared_pool(pool: PostgresPool) -> None:
    """Set the shared pool (called from app lifespan)."""
    global _shared_pool
    _shared_pool = pool


async def close_shared_pool() -> None:
    """Close the shared pool (called from app lifespan shutdown)."""
    global _shared_pool
    if _shared_pool is not None:
        await _shared_pool.disconnect()
        _shared_pool = None
