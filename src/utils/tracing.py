from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def traced_span(_name: str, **_kwargs: Any):
    """Placeholder async tracing context manager."""

    yield
