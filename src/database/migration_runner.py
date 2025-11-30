import hashlib
import importlib.util
from pathlib import Path
import re
import sys
import time
from typing import Any

from chalkbox.logging.bridge import get_logger

from src.database.db_manager import DatabaseManager

logger = get_logger(__name__)


class MigrationRunner:
    """Manages database schema migrations with version tracking."""

    def __init__(self, db_url: str, migrations_dir: Path | None = None):
        self.db_url = db_url
        self.migrations_dir = migrations_dir or self._get_default_migrations_dir()

        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            self.migrations_dir.mkdir(parents=True, exist_ok=True)

    def _get_default_migrations_dir(self) -> Path:
        """Get default migrations directory path."""
        # Try to find project root (where pyproject.toml is)
        current = Path(__file__).parent
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                return current / "scripts" / "migrations"
            current = current.parent

        return Path(__file__).parent.parent.parent / "scripts" / "migrations"

    @staticmethod
    def _ensure_migrations_table(conn):
        """Ensure schema_migrations table exists."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(4) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checksum VARCHAR(64),
                execution_time_ms INTEGER
            )
        """)

    def get_applied_migrations(self, conn) -> dict[str, dict[str, Any]]:
        """Get list of already-applied migrations."""
        self._ensure_migrations_table(conn)

        result = conn.execute("""
            SELECT version, name, applied_at, checksum, execution_time_ms
            FROM schema_migrations
            ORDER BY version
        """).fetchall()

        return {
            row[0]: {
                "version": row[0],
                "name": row[1],
                "applied_at": row[2],
                "checksum": row[3],
                "execution_time_ms": row[4],
            }
            for row in result
        }

    def get_migration_files(self) -> list[tuple[str, str, Path]]:
        """Get all migration files in order.

        Raises:
            ValueError: If duplicate version numbers are found
        """
        migration_files = []
        seen_versions: dict[str, list[str]] = {}

        for file_path in sorted(self.migrations_dir.glob("*.py")):
            if file_path.name.startswith("__"):
                continue

            match = re.match(r"^(\d{4})_(.+)\.py$", file_path.name)
            if not match:
                logger.warning(f"Skipping invalid migration filename: {file_path.name}")
                continue

            version, name = match.groups()

            if version not in seen_versions:
                seen_versions[version] = []
            seen_versions[version].append(file_path.name)

            migration_files.append((version, name, file_path))

        duplicates = {v: files for v, files in seen_versions.items() if len(files) > 1}
        if duplicates:
            error_msg = "Duplicate migration version numbers found:\n"
            for version, files in duplicates.items():
                error_msg += f"  Version {version}:\n"
                for file in files:
                    error_msg += f"    - {file}\n"
            error_msg += "\nEach migration must have a unique version number."
            raise ValueError(error_msg)

        return migration_files

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of migration file."""
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    def _load_migration_module(self, file_path: Path):
        """Dynamically load migration module."""
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not load migration: {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[file_path.stem] = module
        spec.loader.exec_module(module)

        return module

    def _verify_migration_interface(self, module, file_path: Path):
        """Verify migration module has required functions.

        Raises:
            ValueError: If migration doesn't have required functions
        """
        required_functions = ["up"]  # down() is optional
        missing = [f for f in required_functions if not hasattr(module, f)]

        if missing:
            raise ValueError(
                f"Migration {file_path.name} missing required functions: {', '.join(missing)}"
            )

        if not hasattr(module, "check_applied"):
            logger.debug(
                f"Migration {file_path.name} has no check_applied() - assuming not applied"
            )

    def run_migrations(self, dry_run: bool = False) -> dict[str, Any]:
        """Run pending migrations."""

        db = DatabaseManager(self.db_url, read_only=False)

        results: dict[str, Any] = {
            "applied": [],
            "skipped": [],
            "failed": [],
            "total_time_ms": 0,
        }

        start_time = time.time()

        try:
            with db.get_connection() as conn:
                self._ensure_migrations_table(conn)

                applied_migrations = self.get_applied_migrations(conn)
                migration_files = self.get_migration_files()

                if not migration_files:
                    logger.info("No migration files found")
                    return results

                logger.info(f"Found {len(migration_files)} migration file(s)")
                logger.info(f"Already applied: {len(applied_migrations)} migration(s)")

                for version, name, file_path in migration_files:
                    migration_id = f"{version}_{name}"

                    if version in applied_migrations:
                        applied = applied_migrations[version]

                        current_checksum = self._calculate_checksum(file_path)
                        if applied.get("checksum") and applied["checksum"] != current_checksum:
                            logger.warning(
                                f"Migration {migration_id} has been modified since it was applied!"
                            )
                            logger.warning(f"  Applied checksum:  {applied['checksum']}")
                            logger.warning(f"  Current checksum:  {current_checksum}")

                        logger.debug(
                            f"Skipping {migration_id} (already applied on {applied['applied_at']})"
                        )
                        results["skipped"].append({"version": version, "name": name})
                        continue

                    try:
                        module = self._load_migration_module(file_path)
                        self._verify_migration_interface(module, file_path)
                    except Exception as e:
                        logger.error(f"Failed to load migration {migration_id}: {e}")
                        results["failed"].append(
                            {"version": version, "name": name, "error": str(e)}
                        )
                        continue

                    if hasattr(module, "check_applied"):
                        try:
                            if module.check_applied(conn):
                                logger.info(
                                    f"Migration {migration_id} reports already applied "
                                    "(via check_applied) but not tracked - recording..."
                                )
                                if not dry_run:
                                    checksum = self._calculate_checksum(file_path)
                                    conn.execute(
                                        """
                                        INSERT INTO schema_migrations (version, name, checksum, execution_time_ms)
                                        VALUES (?, ?, ?, 0)
                                        """,
                                        [version, name, checksum],
                                    )
                                results["skipped"].append({"version": version, "name": name})
                                continue
                        except Exception as e:
                            logger.warning(f"check_applied() failed for {migration_id}: {e}")

                    logger.info(
                        f"{'[DRY RUN] ' if dry_run else ''}Applying migration: {migration_id}"
                    )

                    if dry_run:
                        results["applied"].append(
                            {"version": version, "name": name, "dry_run": True}
                        )
                        continue

                    migration_start = time.time()
                    try:
                        module.up(conn)

                        execution_time_ms = int((time.time() - migration_start) * 1000)
                        checksum = self._calculate_checksum(file_path)

                        conn.execute(
                            """
                            INSERT INTO schema_migrations (version, name, checksum, execution_time_ms)
                            VALUES (?, ?, ?, ?)
                            """,
                            [version, name, checksum, execution_time_ms],
                        )

                        logger.info(f"✓ Applied {migration_id} ({execution_time_ms}ms)")
                        results["applied"].append(
                            {
                                "version": version,
                                "name": name,
                                "execution_time_ms": execution_time_ms,
                            }
                        )

                    except Exception as e:
                        logger.error(f"✗ Failed to apply {migration_id}: {e}")
                        results["failed"].append(
                            {"version": version, "name": name, "error": str(e)}
                        )

                        break

        except Exception as e:
            logger.error(f"Migration runner failed: {e}")
            results["failed"].append({"error": str(e)})

        results["total_time_ms"] = int((time.time() - start_time) * 1000)

        return results

    def rollback_multiple(self, count: int = 1) -> dict[str, Any]:
        """Rollback last N applied migrations."""

        db = DatabaseManager(self.db_url, read_only=False)

        result: dict[str, Any] = {
            "success": True,
            "rolled_back": [],
            "failed": [],
            "message": "",
        }

        try:
            with db.get_connection() as conn:
                self._ensure_migrations_table(conn)

                migrations = conn.execute(
                    f"""
                    SELECT version, name FROM schema_migrations
                    ORDER BY version DESC LIMIT {count}
                    """
                ).fetchall()

                if not migrations:
                    result["success"] = False
                    result["message"] = "No migrations to rollback"
                    logger.info(result["message"])
                    return result

                if len(migrations) < count:
                    logger.warning(
                        f"Only {len(migrations)} migration(s) available, but {count} requested"
                    )

                for version, name in migrations:
                    migration_id = f"{version}_{name}"

                    try:
                        file_path = self.migrations_dir / f"{version}_{name}.py"
                        if not file_path.exists():
                            error_msg = f"Migration file not found: {file_path.name}"
                            result["failed"].append({"migration": migration_id, "error": error_msg})
                            logger.error(error_msg)
                            result["success"] = False
                            break

                        module = self._load_migration_module(file_path)

                        if not hasattr(module, "down"):
                            error_msg = f"Migration {migration_id} has no down() function"
                            result["failed"].append({"migration": migration_id, "error": error_msg})
                            logger.error(error_msg)
                            result["success"] = False
                            break

                        logger.info(f"Rolling back migration: {migration_id}")
                        module.down(conn)

                        conn.execute("DELETE FROM schema_migrations WHERE version = ?", [version])

                        result["rolled_back"].append(migration_id)
                        logger.info(f"✓ Rolled back {migration_id}")

                    except Exception as e:
                        error_msg = f"Rollback failed for {migration_id}: {e}"
                        result["failed"].append({"migration": migration_id, "error": str(e)})
                        logger.error(error_msg)
                        result["success"] = False
                        break

                if result["rolled_back"]:
                    result["message"] = f"✓ Rolled back {len(result['rolled_back'])} migration(s)"
                    if result["failed"]:
                        result["message"] += f", {len(result['failed'])} failed (stopped early)"
                else:
                    result["message"] = "No migrations were rolled back"

        except Exception as e:
            result["success"] = False
            result["message"] = f"Rollback failed: {e}"
            logger.error(result["message"])

        return result

    def rollback_last(self) -> dict[str, Any]:
        """Rollback the last applied migration."""
        result = self.rollback_multiple(count=1)

        return {"success": result["success"], "message": result["message"]}

    def get_status(self) -> dict[str, Any]:
        """Get migration status."""

        db = DatabaseManager(self.db_url, read_only=False)

        _status: dict[str, Any] = {
            "applied_count": 0,
            "pending_count": 0,
            "applied": [],
            "pending": [],
        }

        try:
            with db.get_connection() as conn:
                self._ensure_migrations_table(conn)

                applied_migrations = self.get_applied_migrations(conn)
                migration_files = self.get_migration_files()

                _status["applied_count"] = len(applied_migrations)
                _status["applied"] = list(applied_migrations.values())

                for version, name, _file_path in migration_files:
                    if version not in applied_migrations:
                        _status["pending"].append({"version": version, "name": name})

                _status["pending_count"] = len(_status["pending"])

        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            _status["error"] = str(e)

        return _status
