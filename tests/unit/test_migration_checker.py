from pathlib import Path

from src.database.db_manager import DatabaseManager
from src.database.migration_checker import (
    check_migrations_required,
    is_command_exempt,
)
from src.database.migration_runner import MigrationRunner


def test_is_command_exempt_for_db_and_help():
    assert is_command_exempt(None) is True
    assert is_command_exempt("db") is True
    assert is_command_exempt("db", "migrate") is True
    assert is_command_exempt("track") is False


def test_check_migrations_required_allows_missing_database(tmp_path: Path):
    db_path = tmp_path / "missing.duckdb"

    status = check_migrations_required(db_path)

    assert status.blocked is False
    assert status.db_exists is False


def test_check_migrations_required_blocks_pending_migrations(tmp_path: Path, migrations_dir: Path):
    db_path = tmp_path / "test.duckdb"
    manager = DatabaseManager(str(db_path), read_only=False)
    manager.create_tables()

    runner = MigrationRunner(str(db_path), migrations_dir=migrations_dir)
    status_before = runner.get_status()
    assert status_before["pending_count"] == 1

    result = check_migrations_required(db_path, migrations_dir=migrations_dir)

    assert result.blocked is True
    assert result.pending_count == 1
    assert result.pending_migrations[0] == "0001_test_migration"


def test_check_migrations_required_allows_up_to_date_database(tmp_path: Path, migrations_dir: Path):
    db_path = tmp_path / "test.duckdb"
    manager = DatabaseManager(str(db_path), read_only=False)
    manager.create_tables()

    runner = MigrationRunner(str(db_path), migrations_dir=migrations_dir)
    runner.run_migrations()

    result = check_migrations_required(db_path, migrations_dir=migrations_dir)

    assert result.blocked is False
    assert result.pending_count == 0
