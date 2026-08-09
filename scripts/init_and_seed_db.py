import asyncio
import os
import sys
from pathlib import Path
import asyncpg

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from app.config import get_settings


async def init_and_seed() -> None:
    settings = get_settings()
    print(f"Connecting to PostgreSQL at {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}...")

    try:
        from db.migrator import MigrationManager
        migrator = MigrationManager()
        await migrator.run_migrations()
        print("✓ All database schema migrations completed successfully.")
    except Exception as exc:
        print(f"Failed to run database migrations: {exc}")
        print("Ensure PostgreSQL is running and credentials in .env are correct.")


if __name__ == "__main__":
    asyncio.run(init_and_seed())
