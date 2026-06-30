import json
from pathlib import Path
import sys
from typing import cast

from chalkbox import Spinner
import click

from src.cli.chalkbox_helpers import (
    show_database_health,
    show_error,
    show_info,
    show_warning,
)
from src.cli.helpers import get_console, get_db_url
from src.database.db_manager import DatabaseManager
from src.database.migration_runner import MigrationRunner

console = get_console()


def _cleanup_data_files(db_url: str) -> None:
    """
    Clean up all data files after database reset.

    Removes:
    - All Parquet export files (snapshots, tracked_pages, product_groups, page_groups)
    - Temporary Parquet files (*.tmp.parquet)
    - DuckDB UI database files (ui.db, ui.db.wal)

    Keeps:
    - Main DuckDB database file (will be reset, not deleted)
    """
    db_path = Path(db_url)
    data_dir = db_path.parent

    parquet_files = [
        data_dir / "snapshots.parquet",
        data_dir / "tracked_pages.parquet",
        data_dir / "product_groups.parquet",
        data_dir / "page_groups.parquet",
    ]

    for parquet_file in parquet_files:
        if parquet_file.exists():
            parquet_file.unlink()

    # Remove all temporary Parquet files created during partial writes (*.tmp.parquet)
    for tmp_file in data_dir.glob("*.tmp.parquet"):
        tmp_file.unlink()

    # DuckDB UI keeps its own mini DB with WAL (those will be cleaned separately)
    ui_dir = data_dir / "ui"
    if ui_dir.exists():
        for ui_file in ["ui.db", "ui.db.wal"]:
            ui_path = ui_dir / ui_file
            if ui_path.exists():
                ui_path.unlink()


@click.group()
@click.pass_context
def db(ctx: click.Context):
    """Database management commands for DuckDB database: reset, info, backup, etc."""
    pass


@db.command()
def init():
    """Initialize a new database with the required schema."""
    db_url = get_db_url()

    if Path(db_url).exists():
        console.print("\n[yellow]Database already exists[/yellow]")
        console.print(f"Location: {db_url}")
        console.print("\nDo you want to reset the database and reinitialize with empty tables?")
        console.print("[dim]This will delete all existing data.[/dim]")
        console.print("\nType 'yes' to reset and reinitialize, or anything else to cancel:")

        try:
            user_input = input("> ").strip().lower()
            if user_input != "yes":
                console.print("[dim]Database initialization cancelled.[/dim]")
                console.print(
                    "\n[dim]Tip: Use 'price-scout db reset' to reset without confirmation.[/dim]"
                )
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Database initialization cancelled.[/dim]")
            return

        # User confirmed (reset the database first)
        try:
            db_manager = DatabaseManager(db_url, read_only=False)

            console.print()
            with Spinner("Resetting database...") as spinner:
                spinner.update("Dropping all tables...")
                db_manager.drop_tables()

                spinner.update("Cleaning up data files...")
                _cleanup_data_files(db_url)

                spinner.update("Recreating schema...")
                db_manager.create_tables()

                spinner.update("Creating Parquet exports for DuckDB UI...")
                db_manager.export_snapshots_to_parquet()

                spinner.success("Database reset and reinitialized successfully!")

            show_info("Ready to track products", details="Use: price-scout track --url <URL>")
            console.print()

        except Exception as e:
            show_error("Error resetting and reinitializing database", details=str(e))
            raise click.Abort() from e

    else:
        # Database doesn't exist (create new one)
        try:
            console.print()
            with Spinner(f"Creating new database at {db_url}") as spinner:
                db_manager = DatabaseManager(db_url, read_only=False)
                db_manager.create_tables()
                spinner.update("Creating Parquet exports for DuckDB UI...")
                db_manager.export_snapshots_to_parquet()
                spinner.success("Database initialized successfully!")

            show_info("Ready to track products", details="Use: price-scout track --url <URL>")
            console.print()

        except Exception as e:
            show_error("Error initializing database", details=str(e))
            raise click.Abort() from e


@db.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def reset(yes: bool):
    """
    Reset the database by dropping all tables and recreating the schema.

    WARNING: This will DELETE ALL tracked products, snapshots, and groups!!!
    """
    db_url = get_db_url()

    console.print("\n[yellow]WARNING: Database Reset[/yellow]")
    console.print(f"Database: {db_url}")
    console.print("\nThis will permanently delete:")
    console.print("  • All page snapshots (price history)")
    console.print("  • All tracked pages")
    console.print("  • All product groups")
    console.print("  • All group associations")
    console.print("  • All Parquet export files")
    console.print("  • DuckDB UI database")

    if not yes:
        console.print("\n[red]This action cannot be undone![/red]")
        console.print("\nType 'yes' to confirm or anything else to cancel:")

        try:
            user_input = input("> ").strip().lower()
            if user_input != "yes":
                console.print("[dim]Database reset cancelled.[/dim]")
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Database reset cancelled.[/dim]")
            return

    try:
        db_manager = DatabaseManager(db_url, read_only=False)

        console.print()
        with Spinner("Dropping all tables...") as spinner:
            db_manager.drop_tables()

            spinner.update("Cleaning up data files...")
            _cleanup_data_files(db_url)

            spinner.update("Recreating schema...")
            db_manager.create_tables()

            spinner.update("Creating empty Parquet exports for DuckDB UI...")
            db_manager.export_snapshots_to_parquet()

            spinner.success("Database reset successfully!")

        show_info(
            "Database reset complete",
            details=f"Location: {db_url}\nAll data files cleaned\nDuckDB UI can now query empty tables without errors",
        )
        console.print()

    except Exception as e:
        show_error("Error resetting database", details=str(e))
        raise click.Abort() from e


@db.command()
def info():
    """Show database information and statistics."""
    db_url = get_db_url()

    try:
        db_manager = DatabaseManager(db_url)

        db_path = Path(db_url)

        if not db_path.exists():
            console.print()
            show_warning(
                "Database file does not exist",
                details=(
                    "The database has not been initialized yet.\n\n"
                    "It will be created automatically when you:\n"
                    "  • Track your first product: price-scout track --url <URL>\n"
                    "  • Or initialize manually: price-scout db init"
                ),
            )
            console.print()
            return

        size_mb = db_path.stat().st_size / (1024 * 1024)

        with db_manager.get_connection() as conn:
            page_snapshots = conn.execute("SELECT COUNT(*) FROM page_snapshots").fetchone()
            tracked_pages = conn.execute("SELECT COUNT(*) FROM tracked_pages").fetchone()
            product_groups = conn.execute("SELECT COUNT(*) FROM product_groups").fetchone()
            providers = conn.execute(
                "SELECT COUNT(DISTINCT provider) FROM page_snapshots"
            ).fetchone()

            page_snapshots_range = conn.execute(
                "SELECT MIN(scraped_at), MAX(scraped_at) FROM page_snapshots"
            ).fetchone()

            # Extract timestamps if available
            oldest_snapshot = str(page_snapshots_range[0]) if page_snapshots_range[0] else None
            latest_snapshot = str(page_snapshots_range[1]) if page_snapshots_range[1] else None

            console.print()
            show_database_health(
                db_url=db_url,
                size_mb=size_mb,
                page_snapshots=page_snapshots[0],
                tracked_pages=tracked_pages[0],
                product_groups=product_groups[0],
                providers=providers[0],
                oldest_snapshot=oldest_snapshot,
                latest_snapshot=latest_snapshot,
            )
            console.print()

    except Exception as e:
        show_error("Error getting database info", details=str(e))
        raise click.Abort() from e


@db.group()
def migrate():
    """Database migration commands."""
    pass


@migrate.command(name="apply")
@click.option("--dry-run", is_flag=True, help="Show what would be applied without executing")
def migrate_apply(dry_run: bool):
    """Apply pending database migrations."""

    db_url = get_db_url()

    try:
        console.print()
        if dry_run:
            show_info("DRY RUN", details="Showing what would be applied (no changes will be made)")
            console.print()

        runner = MigrationRunner(db_url)
        results = runner.run_migrations(dry_run=dry_run)

        console.print()
        if results["applied"]:
            console.print(f"[green]✓ Applied {len(results['applied'])} migration(s):[/green]")
            for migration in results["applied"]:
                version = migration["version"]
                name = migration["name"]
                if migration.get("dry_run"):
                    console.print(f"  [dim]• {version}_{name} (dry run)[/dim]")
                else:
                    time_ms = migration.get("execution_time_ms", 0)
                    console.print(f"  [dim]• {version}_{name} ({time_ms}ms)[/dim]")
            console.print()

        if results["skipped"]:
            console.print(
                f"[dim]Skipped {len(results['skipped'])} already-applied migration(s)[/dim]"
            )
            console.print()

        if results["failed"]:
            console.print(f"[red]✗ Failed {len(results['failed'])} migration(s):[/red]")
            for migration in results["failed"]:
                if "error" in migration:
                    console.print(f"  [red]• {migration.get('error', 'Unknown error')}[/red]")
                else:
                    version = migration.get("version", "unknown")
                    name = migration.get("name", "unknown")
                    error = migration.get("error", "Unknown error")
                    console.print(f"  [red]• {version}_{name}: {error}[/red]")
            console.print()
            raise click.Abort()

        if not results["applied"] and not results["failed"]:
            show_info("No pending migrations", details="All migrations are up to date")
            console.print()

    except click.Abort:
        raise
    except Exception as e:
        show_error("Migration failed", details=str(e))
        raise click.Abort() from e


@migrate.command()
@click.option("--json", "as_json", is_flag=True, help="Output status as JSON")
def status(as_json: bool):
    """Show migration status."""

    db_url = get_db_url()

    try:
        runner = MigrationRunner(db_url)
        status_info = runner.get_status()

        if as_json:
            click.echo(json.dumps(status_info, indent=2, default=str))
            return

        console.print()
        console.print("[bold]Migration Status[/bold]")
        console.print()

        # Applied migrations
        console.print(f"[green]Applied: {status_info['applied_count']} migration(s)[/green]")
        if status_info["applied"]:
            for migration in status_info["applied"]:
                version = migration["version"]
                name = migration["name"]
                applied_at = migration.get("applied_at", "Unknown")
                console.print(f"  [dim]• {version}_{name} (applied: {applied_at})[/dim]")
        console.print()

        if status_info["pending_count"] > 0:
            console.print(f"[yellow]Pending: {status_info['pending_count']} migration(s)[/yellow]")
            for migration in status_info["pending"]:
                version = migration["version"]
                name = migration["name"]
                console.print(f"  [dim]• {version}_{name}[/dim]")
            console.print()
            console.print(
                "[yellow]Run 'scout db migrate apply' to apply pending migrations[/yellow]"
            )
        else:
            console.print("[green]✓ All migrations up to date[/green]")

        console.print()

    except Exception as e:
        show_error("Failed to get migration status", details=str(e))
        raise click.Abort() from e


@migrate.command(name="check")
def migrate_check():
    """Check migration status using exit codes for automation.

    Exit codes:
      0 - All migrations up to date
      1 - Pending migrations need to be applied
      2 - Error checking migration status
    """
    db_url = get_db_url()

    try:
        runner = MigrationRunner(db_url)
        status_info = runner.get_status()

        if status_info.get("error"):
            click.echo(status_info["error"], err=True)
            sys.exit(2)

        if status_info.get("pending_count", 0) > 0:
            sys.exit(1)

        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        click.echo(str(e), err=True)
        sys.exit(2)


@migrate.command()
@click.argument("count", type=int, default=1, required=False)
def rollback(count: int):
    """Rollback the last N applied migration(s)."""

    db_url = get_db_url()

    try:
        console.print()

        runner = MigrationRunner(db_url)
        status_info = runner.get_status()

        if status_info["applied_count"] == 0:
            show_info("No migrations to rollback", details="Database is empty")
            console.print()
            return

        migrations_to_rollback = status_info["applied"][-count:]  # Last N migrations
        actual_count = min(count, len(status_info["applied"]))

        if actual_count < count:
            show_warning(
                f"Only {actual_count} migration(s) available",
                details=f"You requested {count}, but only {actual_count} exist",
            )

        console.print("[yellow]The following migration(s) will be rolled back:[/yellow]")
        for migration in reversed(migrations_to_rollback):  # Show newest first
            version = migration["version"]
            name = migration["name"]
            console.print(f"  [dim]• {version}_{name}[/dim]")
        console.print()

        try:
            user_input = (
                input(f"Are you sure you want to rollback {actual_count} migration(s)? [y/N]: ")
                .strip()
                .lower()
            )
            if user_input not in ["y", "yes"]:
                console.print("[dim]Rollback cancelled.[/dim]")
                console.print()
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Rollback cancelled.[/dim]")
            console.print()
            return

        show_warning(
            "Rolling back migrations",
            details="This will undo database changes. Make sure you have a backup!",
        )
        console.print()

        result = runner.rollback_multiple(count)

        console.print()
        if result["rolled_back"]:
            console.print(
                f"[green]✓ Successfully rolled back {len(result['rolled_back'])} migration(s):[/green]"
            )
            for migration_id in result["rolled_back"]:
                console.print(f"  [dim]• {migration_id}[/dim]")

        if result["failed"]:
            console.print()
            console.print(f"[red]✗ Failed to rollback {len(result['failed'])} migration(s):[/red]")
            for failure in result["failed"]:
                migration = failure.get("migration", "unknown")
                error = failure.get("error", "unknown error")
                console.print(f"  [red]• {migration}: {error}[/red]")

        if not result["success"]:
            console.print()
            raise click.Abort()

        console.print()

    except click.Abort:
        raise
    except Exception as e:
        show_error("Rollback failed", details=str(e))
        raise click.Abort() from e


db = cast(click.Group, db)
