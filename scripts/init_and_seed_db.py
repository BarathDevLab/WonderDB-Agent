import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from app.config import get_settings


async def init_and_seed() -> None:
    settings = get_settings()
    print(f"Connecting to PostgreSQL database '{settings.postgres_db}' at {settings.postgres_host}:{settings.postgres_port}...")

    try:
        from db.postgres import PostgresPool
        from services.schema_rag import sync_schema_catalog

        # Sync schema catalog vector embeddings for pgvector RAG
        pool = PostgresPool(settings)
        for tenant_id in [
            "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
        ]:
            count = await sync_schema_catalog(tenant_id, pool, api_key=settings.gemini_api_key)
            print(f"  [OK] Synchronized {count} pgvector schema embeddings for tenant {tenant_id}.")

        await pool.disconnect()
        print("[OK] Database initialization and pgvector schema RAG seeding complete.")
    except Exception as exc:
        print(f"Failed to run database migrations: {exc}")
        print("Ensure PostgreSQL is running and credentials in .env are correct.")


if __name__ == "__main__":
    asyncio.run(init_and_seed())
