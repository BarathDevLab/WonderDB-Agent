from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.config import Settings, get_settings


class PostgresPool:
    """Asyncpg pool manager used by API handlers and services."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._settings.postgres_dsn,
            min_size=1,
            max_size=10,
            command_timeout=10,
        )

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
            raise RuntimeError("Postgres pool is not initialized.")

        async with self._pool.acquire() as conn:
            yield conn
