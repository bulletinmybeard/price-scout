"""Migration checker for CLI startup validation.

This module provides functions to check migration status and block CLI commands
when pending migrations exist. It ensures schema consistency before any database
operations.
"""

from dataclasses import dataclass
from pathlib import Path

from chalkbox.logging.bridge import get_logger

from src.database.migration_runner import MigrationRunner

logger = get_logger(__name__)


# Commands that are allowed without migration check
MIGRATION_EXEMPT_COMMANDS: frozenset[str | None] = frozenset(
    {
        "db",  # Parent command for migrate subcommands
        None,  # No subcommand (shows help)
    }
)

# Subcommands under 'db' that are always allowed
MIGRATION_EXEMPT_DB_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "migrate",
        "init",
    }
)


@dataclass
class MigrationStatus:
    """Result of migration check."""

    blocked: bool
    pending_count: int
    pending_migrations: list[str]
    message: str
    db_exists: bool
    schema_migrations_exists: bool


def check_migrations_required(db_path: str | Path) -> MigrationStatus:
    """Check if database needs migrations before CLI operations.

    This function determines whether the CLI should block execution due to
    pending migrations. It handles several scenarios:

    1. Database doesn't exist: Allow (fresh install, tables created on first use)
    2. Database exists, no schema_migrations table: Block (upgrade path)
    3. Database exists, schema_migrations exists, no pending: Allow
    4. Database exists, schema_migrations exists, pending migrations: Block

    For the upgrade path (scenario 2), running `scout db migrate apply` will:
    - Create the schema_migrations table
    - Auto-detect already-applied migrations via check_applied() functions
    - Only apply genuinely pending migrations

    Args:
        db_path: Path to the DuckDB database file

    Returns:
        MigrationStatus with blocked flag and descriptive message
    """
    db_path = Path(db_path)

    if not db_path.exists():
        logger.debug(f"Database does not exist: {db_path}")
        return MigrationStatus(
            blocked=False,
            pending_count=0,
            pending_migrations=[],
            message="Fresh installation - database will be created on first use",
            db_exists=False,
            schema_migrations_exists=False,
        )

    try:
        runner = MigrationRunner(str(db_path))
        status = runner.get_status()

        pending_count = status.get("pending_count", 0)
        pending = status.get("pending", [])
        pending_names = [f"{m['version']}_{m['name']}" for m in pending]

        if status.get("error"):
            logger.debug(f"Migration status check failed: {status['error']}")
            return MigrationStatus(
                blocked=True,
                pending_count=0,
                pending_migrations=[],
                message=f"Migration check failed: {status['error']}",
                db_exists=True,
                schema_migrations_exists=False,
            )

        if pending_count > 0:
            message = _build_blocking_message(db_path, pending_count, pending_names)
            return MigrationStatus(
                blocked=True,
                pending_count=pending_count,
                pending_migrations=pending_names,
                message=message,
                db_exists=True,
                schema_migrations_exists=True,
            )

        logger.debug("All migrations up to date")
        return MigrationStatus(
            blocked=False,
            pending_count=0,
            pending_migrations=[],
            message="All migrations up to date",
            db_exists=True,
            schema_migrations_exists=True,
        )

    except Exception as e:
        logger.debug(f"Migration check error: {e}")
        return MigrationStatus(
            blocked=True,
            pending_count=0,
            pending_migrations=[],
            message=f"Migration check failed: {e}",
            db_exists=True,
            schema_migrations_exists=False,
        )


def _build_blocking_message(db_path: Path, pending_count: int, pending_names: list[str]) -> str:
    """Build user-friendly error message for pending migrations."""
    migrations_list = "\n".join(f"  - {name}" for name in pending_names)

    return f"""Database requires migrations before this operation.

Your database version is behind the application version.
Pending migrations: {pending_count}
{migrations_list}

To apply migrations:
  1. Backup your database (recommended):
     cp {db_path} {db_path}.backup

  2. Apply migrations:
     scout db migrate apply

Run 'scout db migrate status' to see migration details."""


def is_command_exempt(command: str | None, subcommand: str | None = None) -> bool:
    """Check if a command is exempt from migration checks.

    Args:
        command: The main CLI command (e.g., 'track', 'db', 'groups')
        subcommand: The subcommand if applicable (e.g., 'migrate' under 'db')

    Returns:
        True if the command should bypass migration checks
    """
    return command in MIGRATION_EXEMPT_COMMANDS or (
        command == "db" and subcommand in MIGRATION_EXEMPT_DB_SUBCOMMANDS
    )
