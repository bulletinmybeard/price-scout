import logging
from pathlib import Path
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
    debug = ctx.obj.get("debug", False)

    if not debug:
        # Only show warnings and errors
        logging.getLogger().setLevel(logging.WARNING)
        for logger_name in ["src", "config", "playwright", "urllib3", "asyncio"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


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


db = cast(click.Group, db)
