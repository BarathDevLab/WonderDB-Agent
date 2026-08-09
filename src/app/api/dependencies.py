from typing import Any


async def get_tenant_context() -> dict[str, Any]:
    """Placeholder dependency for tenant-scoped request context."""

    return {"tenant_id": "default-tenant"}
