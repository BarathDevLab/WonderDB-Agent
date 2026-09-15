from db.migrator import MigrationManager


def test_migration_manager_uses_the_configured_migration_directory(tmp_path) -> None:
    expected = [
        "001_initial_extensions_and_roles.sql",
        "002_create_core_tables.sql",
        "003_enable_rls_and_policies.sql",
        "004_seed_initial_data.sql",
    ]
    for filename in reversed(expected):
        (tmp_path / filename).write_text("SELECT 1;", encoding="utf-8")
    migrator = MigrationManager(migrations_dir=tmp_path)
    files = sorted([f.name for f in migrator._migrations_dir.glob("*.sql")])

    assert files == expected
