from contextlib import redirect_stderr
from io import StringIO
import json
import sys
from typing import Any, cast

from chalkbox.logging.bridge import get_logger
import click

from src.cli.chalkbox_helpers import show_error
from src.cli.formatters import (
    display_comparison_table_with_changes,
    output_multi_json_response,
)
from src.cli.helpers import get_console, get_db_url
from src.config.config_loader import load_typed_config
from src.database.db_manager import DatabaseManager
from src.price_tracker.bulk_tracker import BulkTracker
from src.price_tracker.group_helpers import handle_fuzzy_group_matching
from src.price_tracker.tracker import PriceTracker
from src.providers import get_factory

logger = get_logger(__name__)


def _handle_delete_products(urls: list[str], skip_confirmation: bool, json_output: bool):
    console = get_console()
    db_url = get_db_url()
    db = DatabaseManager(db_url, read_only=False)

    deletion_results: list[dict[str, Any]] = []
    all_orphaned_groups = set()

    for url in urls:
        try:
            page = db.get_tracked_page(url)
            if not page:
                deletion_results.append(
                    {"url": url, "status": "error", "error": "URL not found in tracked pages"}
                )
                continue

            with db.get_connection() as conn:
                snapshot_count_result = conn.execute(
                    "SELECT COUNT(*) FROM page_snapshots WHERE url = ?", [url]
                ).fetchone()
                snapshot_count = snapshot_count_result[0] if snapshot_count_result else 0

            deletion_results.append(
                {
                    "url": url,
                    "status": "pending",
                    "page_id": page["id"],
                    "provider": page["provider"],
                    "snapshot_count": snapshot_count,
                }
            )

        except Exception as e:
            deletion_results.append({"url": url, "status": "error", "error": str(e)})

    valid_deletions = [r for r in deletion_results if r["status"] == "pending"]

    if not valid_deletions:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "status": "error",
                        "message": "No valid URLs to delete",
                        "results": deletion_results,
                    },
                    indent=2,
                )
            )
        else:
            show_error("No valid URLs to delete", details="Check that URLs are tracked")
        return

    if not json_output:
        console.print()
        console.print(f"[yellow]Deleting {len(valid_deletions)} tracked product(s):[/yellow]")
        for result in valid_deletions:
            console.print(f"\n  [bold]{result['url'][:80]}...[/bold]")
            console.print(f"  Provider: {result['provider']}")
            console.print(f"  Price history snapshots: {result['snapshot_count']}")
        console.print()

    if not skip_confirmation:
        console.print("[red]This will permanently delete ALL data for these products:[/red]")
        console.print("  - All price history snapshots")
        console.print("  - Tracked page records")
        console.print("  - Product group associations")
        console.print()

        try:
            user_input = (
                input(f"Are you sure you want to delete {len(valid_deletions)} product(s)? [y/N]: ")
                .strip()
                .lower()
            )
            if user_input not in ["y", "yes"]:
                if json_output:
                    click.echo(
                        json.dumps(
                            {"status": "cancelled", "message": "Deletion cancelled by user"},
                            indent=2,
                        )
                    )
                else:
                    console.print("[dim]Deletion cancelled.[/dim]")
                    console.print()
                return
        except (EOFError, KeyboardInterrupt):
            if json_output:
                click.echo(
                    json.dumps(
                        {"status": "cancelled", "message": "Deletion cancelled by user"}, indent=2
                    )
                )
            else:
                console.print("\n[dim]Deletion cancelled.[/dim]")
                console.print()
            return

    for result in valid_deletions:
        try:
            deletion_summary = db.delete_tracked_page(result["url"])
            result["status"] = "deleted"
            result["snapshots_deleted"] = deletion_summary["snapshots_deleted"]
            result["group_associations_removed"] = deletion_summary["group_associations_removed"]
            result["orphaned_groups"] = deletion_summary["orphaned_groups"]

            all_orphaned_groups.update(deletion_summary["orphaned_groups"])

            if not json_output:
                console.print(f"[green]✓ Deleted: {result['url'][:80]}...[/green]")

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            if not json_output:
                console.print(f"[red]✗ Failed: {result['url'][:80]}...[/red]")
                console.print(f"[red]  Error: {e!s}[/red]")

    if all_orphaned_groups and not skip_confirmation and not json_output:
        console.print()
        console.print(
            f"[yellow]Warning: {len(all_orphaned_groups)} product group(s) now empty:[/yellow]"
        )
        for group_name in sorted(all_orphaned_groups):
            console.print(f"  • {group_name}")
        console.print()
        console.print(
            "[dim]Empty groups are kept by default. You can manually delete them via:[/dim]"
        )
        console.print("[dim]  scout groups list  # View all groups[/dim]")
        console.print()

    if json_output:
        click.echo(
            json.dumps(
                {
                    "status": "success",
                    "deleted_count": len([r for r in deletion_results if r["status"] == "deleted"]),
                    "failed_count": len([r for r in deletion_results if r["status"] == "error"]),
                    "orphaned_groups": list(all_orphaned_groups),
                    "results": deletion_results,
                },
                indent=2,
            )
        )
    else:
        console.print()
        deleted = len([r for r in deletion_results if r["status"] == "deleted"])
        failed = len([r for r in deletion_results if r["status"] == "error"])
        console.print(f"[green]✓ Successfully deleted: {deleted} product(s)[/green]")
        if failed > 0:
            console.print(f"[red]✗ Failed: {failed} product(s)[/red]")
        console.print()


@click.command()
@click.option(
    "--url",
    "-u",
    multiple=True,
    required=True,
    help="Product page URL(s) - max 25 URLs for comparison",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON (all BaseProduct fields)")
@click.option("--check", is_flag=True, help="Check product without tracking to database")
@click.option(
    "--cached", is_flag=True, help="Return cached snapshot if available, scrape on cache miss"
)
@click.option(
    "--full", is_flag=True, help="Show all BaseProduct fields (default shows key fields only)"
)
@click.option(
    "--headed/--headless",
    default=None,
    help="Run browser in headed/headless mode. Default: uses config.yaml setting",
)
@click.option(
    "--group",
    "-g",
    default=None,
    help="Assign tracked URL(s) to a product group (creates group if doesn't exist)",
)
@click.option(
    "--delete",
    is_flag=True,
    help="Delete tracked product(s) and ALL related data (snapshots, group associations)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompts (for delete operations)",
)
@click.pass_context
def track(
    ctx,
    url: str,
    json_output: bool,
    check: bool,
    cached: bool,
    full: bool,
    headed: bool | None,
    group: str | None,
    delete: bool,
    yes: bool,
):
    """
    Track one or more products from URLs and compare prices.

    Provider is automatically detected from URL. Supports table or JSON output.
    Multi-URL tracking shows comparison table with latest prices and change indicators.

    Examples:
        # Single URL
        price-scout track --url "https://www.store-a.example/..."
        price-scout track --url "https://www.store-b.example/..." --check
        price-scout track --url "https://www.store-c.example/..." --json

        # Track with product group (creates group if doesn't exist)
        price-scout track --url "URL" --group "Dog Food Comparison"
        price-scout track --url "URL1" --url "URL2" --group "Weekly Groceries"

        # Multi-URL comparison
        price-scout track --url "URL1" --url "URL2" --url "URL3"
        price-scout track --url "URL1" --url "URL2" --cached
        price-scout track --url "URL1" --url "URL2" --url "URL3" --json
        price-scout track --url "URL1" --url "URL2" --check
    """
    unique_urls = list(dict.fromkeys(url))

    if delete:
        return _handle_delete_products(unique_urls, yes, json_output)

    # Load max_parallel_urls from config (default: 25)
    config = load_typed_config()
    max_unique_urls = config.cli.max_parallel_urls

    # Validate max URLs
    if len(unique_urls) > max_unique_urls:
        error_msg = f"Maximum {max_unique_urls} URLs allowed for comparison. You provided {len(unique_urls)} URLs."
        if json_output:
            click.echo(json.dumps({"status": "error", "error": error_msg}, indent=2))
        else:
            show_error(
                f"Maximum {max_unique_urls} URLs allowed",
                details=f"You provided {len(unique_urls)} URLs. Please reduce to {max_unique_urls} or fewer.",
            )
        raise click.Abort()

    # Configure logging based on output mode and debug flag
    ctx.obj.get("debug", False)

    # In JSON mode, suppress stderr to hide event loop cleanup warnings
    stderr_suppressor = StringIO() if json_output else sys.stderr

    # Handle all product URLs with BulkTracker
    try:
        with redirect_stderr(stderr_suppressor):
            # Initialize database and factory (write mode for tracking)
            db_manager = DatabaseManager(get_db_url(), read_only=False)
            # Pass None if user didn't specify, so PriceTracker reads from config.yaml
            headless_mode = None if headed is None else not headed
            tracker = PriceTracker(db_manager, headless=headless_mode)
            provider_config_override = ctx.obj.get("provider_config")
            factory = get_factory(provider_config=provider_config_override)

            # Fuzzy group matching - unified handling
            resolved_group_name = handle_fuzzy_group_matching(group, db_manager, json_output)

            # Use BulkTracker for all URL operations (single or multiple)
            bulk_tracker = BulkTracker(
                tracker=tracker,
                factory=factory,
                db_manager=db_manager,
                check=check,
                cached=cached,
                json_output=json_output,
            )

            # Track all URLs in parallel
            results = bulk_tracker.track_multiple_urls(unique_urls, resolved_group_name)

            # Output results
            if json_output:
                output_multi_json_response(results)
            else:
                # Get latest snapshots with previous for change detection
                snapshots_with_changes = db_manager.get_latest_snapshots_with_previous(unique_urls)

                console = get_console()
                console.print()  # Add blank line before table
                has_valid_snapshots = any(
                    s.get("latest") is not None for s in snapshots_with_changes.values()
                )
                if has_valid_snapshots:
                    display_comparison_table_with_changes(snapshots_with_changes, console)
                else:
                    console.print("[yellow]No snapshots found for comparison.[/yellow]")

            return None

    except click.Abort:
        raise
    except KeyboardInterrupt:
        # BulkTracker already handled graceful shutdown
        return
    except Exception as e:
        error_msg = str(e)
        if json_output:
            output_multi_json_response([], error=error_msg)
        else:
            show_error("Failed to track products", details=error_msg)
        raise click.Abort() from e


track = cast(click.Command, track)
