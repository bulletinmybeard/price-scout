from pathlib import Path
import zipfile

import pytest

from src.database.db_manager import DatabaseManager
from src.database.migration_runner import MigrationRunner, get_default_migrations_dir


def test_get_default_migrations_dir_uses_packaged_migrations():
    migrations_dir = get_default_migrations_dir()
    migration_files = list(migrations_dir.glob("000*.py"))

    assert migrations_dir.name == "migrations"
    assert len(migration_files) >= 3


def test_run_migrations_applies_pending_migration(tmp_path: Path, migrations_dir: Path):
    db_path = tmp_path / "test.duckdb"
    runner = MigrationRunner(str(db_path), migrations_dir=migrations_dir)

    results = runner.run_migrations()

    assert len(results["applied"]) == 1
    assert results["failed"] == []

    status = runner.get_status()
    assert status["pending_count"] == 0
    assert status["applied_count"] == 1


def test_run_migrations_skips_already_applied(tmp_path: Path, migrations_dir: Path):
    db_path = tmp_path / "test.duckdb"
    runner = MigrationRunner(str(db_path), migrations_dir=migrations_dir)

    first = runner.run_migrations()
    second = runner.run_migrations()

    assert len(first["applied"]) == 1
    assert len(second["applied"]) == 0
    assert len(second["skipped"]) == 1


def test_rollback_last_reverses_migration(tmp_path: Path, migrations_dir: Path):
    db_path = tmp_path / "test.duckdb"
    runner = MigrationRunner(str(db_path), migrations_dir=migrations_dir)
    runner.run_migrations()

    result = runner.rollback_last()

    assert result["success"] is True

    with DatabaseManager(str(db_path), read_only=False).get_connection() as conn:
        table_exists = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'migration_test'"
        ).fetchone()
        assert table_exists is None


def test_duplicate_migration_versions_raise_error(tmp_path: Path):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "0001_first.py").write_text("def up(conn): pass\n")
    (migration_dir / "0001_second.py").write_text("def up(conn): pass\n")

    runner = MigrationRunner(str(tmp_path / "test.duckdb"), migrations_dir=migration_dir)

    with pytest.raises(ValueError, match="Duplicate migration version"):
        runner.get_migration_files()


def test_packaged_migrations_included_in_wheel():
    import subprocess

    subprocess.run(["poetry", "build", "-q"], check=True, cwd=Path.cwd())

    dist_dir = Path("dist")
    wheels = sorted(dist_dir.glob("price_scout-*.whl"))
    assert wheels, "Expected wheel build output"

    with zipfile.ZipFile(wheels[-1]) as archive:
        migration_members = [
            name
            for name in archive.namelist()
            if "database/migrations/000" in name and name.endswith(".py")
        ]

    assert len(migration_members) >= 3
