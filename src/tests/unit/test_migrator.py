import pytest
from pathlib import Path
from db.migrator import MigrationManager


def test_migration_manager_discovers_files() -> None:
    migrator = MigrationManager()
    files = sorted([f.name for f in migrator._migrations_dir.glob("*.sql")])

    assert len(files) >= 4
    assert "001_initial_extensions_and_roles.sql" in files
    assert "002_create_core_tables.sql" in files
    assert "003_enable_rls_and_policies.sql" in files
    assert "004_seed_initial_data.sql" in files
