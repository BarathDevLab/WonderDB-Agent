import asyncio
from pathlib import Path
import sys
from typing import Any

_src_root = str(Path(__file__).resolve().parent.parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

import asyncpg

from app.config import get_settings


class MigrationManager:
    """Async migration manager applying ordered SQL migrations with version tracking."""

    def __init__(self, migrations_dir: Path | None = None) -> None:
        self._migrations_dir = migrations_dir or Path(__file__).parent / "migrations"

    async def _ensure_migrations_table(self, conn: asyncpg.Connection) -> None:
        """Create schema_migrations version tracking table if not exists."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
        )

    async def _ensure_database_exists(self, cfg: Any) -> None:
        """Create target database if it does not exist by connecting to maintenance db."""
        if getattr(cfg, "database_url", None) or (cfg.postgres_host not in ("localhost", "127.0.0.1", "")):
            # Managed cloud databases (Render, Neon, Supabase) pre-create the target database
            return
        try:
            conn = await asyncpg.connect(
                user=cfg.postgres_user,
                password=cfg.postgres_password,
                host=cfg.postgres_host,
                port=cfg.postgres_port,
                database="postgres",
            )
            try:
                db_exists = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1;", cfg.postgres_db
                )
                if not db_exists:
                    print(f"Database '{cfg.postgres_db}' does not exist. Creating database...")
                    await conn.execute(f'CREATE DATABASE "{cfg.postgres_db}";')
                    print(f"  [OK] Database '{cfg.postgres_db}' created successfully.")
            finally:
                await conn.close()
        except Exception as exc:
            print(f"[Notice] Database existence check: {exc}")

    async def run_migrations(self, settings: None = None) -> list[str]:
        """Discover and execute pending SQL migration files in numerical order."""
        cfg = settings or get_settings()
        await self._ensure_database_exists(cfg)
        print(f"Connecting to PostgreSQL database via DSN...")

        conn = await asyncpg.connect(dsn=cfg.postgres_dsn)

        try:
            await self._ensure_migrations_table(conn)

            # Get applied migration versions
            applied_records = await conn.fetch("SELECT version FROM schema_migrations;")
            applied_versions = {r["version"] for r in applied_records}

            # Discover SQL migration files
            migration_files = sorted(
                [f for f in self._migrations_dir.glob("*.sql")],
                key=lambda p: p.name,
            )

            executed: list[str] = []
            for file_path in migration_files:
                version_name = file_path.name
                if version_name in applied_versions:
                    print(f"  [Skipped] {version_name} (already applied)")
                    continue

                print(f"  [Applying] {version_name}...")
                sql_content = file_path.read_text(encoding="utf-8")

                async with conn.transaction():
                    await conn.execute(sql_content)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1);",
                        version_name,
                    )
                print(f"  [OK] {version_name} applied successfully.")
                executed.append(version_name)

            if not executed:
                print("Database is up to date. No pending migrations.")
            else:
                print(f"Successfully applied {len(executed)} migration(s).")

            return executed
        finally:
            await conn.close()


async def run_cli() -> None:
    manager = MigrationManager()
    await manager.run_migrations()


if __name__ == "__main__":
    asyncio.run(run_cli())
