from contextlib import redirect_stderr
from io import StringIO
import json
import sys
from typing import Any, Literal, cast

from chalkbox.logging.bridge import get_logger
import click

from src.cli.chalkbox_helpers import show_error, show_info
from src.cli.formatters import (
    display_comparison_table_with_changes,
    display_table_output,
    output_json_response,
    output_multi_json_response,
)
from src.cli.helpers import detect_provider_from_url, get_console, get_db_url
from src.cli.logging_config import configure_logging_for_output_mode
from src.config.config_loader import load_typed_config
from src.database.db_manager import DatabaseManager
from src.price_tracker.bulk_tracker import BulkTracker
from src.price_tracker.group_helpers import (
    associate_tracked_page_with_group,
    auto_associate_with_groups,
    handle_fuzzy_group_matching,
)
from src.price_tracker.tracker import PriceTracker
from src.providers import get_factory
from src.providers.base_product import BaseProduct
from src.utils.datetime_utils import now_in_configured_tz

logger = get_logger(__name__)


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
    debug = ctx.obj.get("debug", False)

    mode: Literal["debug", "json", "table"]
    if debug:
        mode = "debug"
    elif json_output:
        mode = "json"
    else:
        mode = "table"
    configure_logging_for_output_mode(mode, debug)

    # In JSON mode, suppress stderr to hide event loop cleanup warnings
    stderr_suppressor = StringIO() if json_output else sys.stderr

    # Handle multiple URLs with BulkTracker
    if len(unique_urls) > 1:
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

                # Use BulkTracker for multi-URL operations
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
                    snapshots_with_changes = db_manager.get_latest_snapshots_with_previous(
                        unique_urls
                    )

                    console = get_console()
                    console.print()  # Add blank line before table
                    if snapshots_with_changes:
                        display_comparison_table_with_changes(snapshots_with_changes, console)
                    else:
                        console.print("[yellow]No snapshots found for comparison.[/yellow]")

                return

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
                show_error("Failed to track multiple URLs", details=error_msg)
            raise click.Abort() from e

    # SINGLE-URL LOGIC
    try:
        with redirect_stderr(stderr_suppressor):
            # Use first URL for single-URL mode
            single_url = unique_urls[0]

            # Auto-detect provider
            provider_config_override = ctx.obj.get("provider_config")
            factory = get_factory(provider_config=provider_config_override)
            provider_name, _provider_config = detect_provider_from_url(single_url, factory)

            if not provider_name:
                error_msg = f"Could not detect provider for URL: {single_url}\nAvailable providers: {', '.join(factory.list_providers())}"
                if json_output:
                    output_json_response(None, error_msg)
                    return
                else:
                    show_error(
                        "Could not detect provider",
                        details=f"URL: {single_url}\n\nAvailable providers: {', '.join(factory.list_providers())}",
                    )
                    raise click.Abort()

            # Initialize tracker (write mode for tracking)
            db_manager = DatabaseManager(get_db_url(), read_only=False)
            # Pass None if user didn't specify, so PriceTracker reads from config.yaml
            headless_mode = None if headed is None else not headed
            tracker = PriceTracker(db_manager, headless=headless_mode)

            # Fuzzy group matching - unified handling
            resolved_group_name = handle_fuzzy_group_matching(group, db_manager, json_output)

            # Check cache if --cached flag is set
            if cached:
                cached_snapshot = db_manager.get_latest_snapshot(single_url)
                if cached_snapshot:
                    # Cache HIT - return cached snapshot data immediately
                    if json_output:
                        # Output the full snapshot as JSON
                        click.echo(json.dumps(cached_snapshot, indent=2, default=str))
                        return
                    else:
                        # Display cache hit message and snapshot summary
                        console = get_console()
                        console.print("[green]✓ Cache HIT[/green] - Returning cached snapshot")
                        console.print(
                            f"[dim]Scraped at: {cached_snapshot.get('scraped_at')}[/dim]\n"
                        )

                        # Convert snapshot to minimal product-like dict for display
                        _product_display = {
                            "name": cached_snapshot.get("name"),
                            "brand": cached_snapshot.get("brand"),
                            "current_price": cached_snapshot.get("current_price"),
                            "currency": cached_snapshot.get("currency"),
                            "availability": cached_snapshot.get("availability"),
                            "provider": cached_snapshot.get("provider"),
                        }
                        db_result = {
                            "snapshot_id": cached_snapshot.get("snapshot_id"),
                            "product_name": cached_snapshot.get("name"),
                            "provider": cached_snapshot.get("provider"),
                            "price": cached_snapshot.get("current_price"),
                            "currency": cached_snapshot.get("currency"),
                            "is_available": cached_snapshot.get("availability"),
                            "scraped_at": cached_snapshot.get("scraped_at"),
                        }

                        # Create a mock product object for display
                        product = BaseProduct(
                            url=single_url,
                            name=cached_snapshot.get("name") or "Unknown",
                            brand=cached_snapshot.get("brand"),
                            current_price=cached_snapshot.get("current_price"),
                            currency=cached_snapshot.get("currency") or "EUR",
                            availability=bool(cached_snapshot.get("availability")),
                            extraction_method="cached",
                        )
                        display_table_output(product, db_result, full, console)
                        return
                else:
                    # Cache MISS - continue with normal scraping
                    if not json_output:
                        show_info(
                            "Cache MISS",
                            details="No cached data found. Fetching fresh product data...",
                        )

            # Track or check product
            db_result_tracking: dict[Any, Any] | None
            if check:
                # Fetch only, no DB tracking
                product = tracker.fetch_product_only(single_url, provider_name)
                db_result_tracking = None
            else:
                # Full tracking with DB
                product, db_result_tracking = tracker.track_product_url(
                    single_url, provider_name, track_to_db=True
                )

                # Check if URL was canonicalized and show info message
                if product and product.raw_data.get("_canonicalization", {}).get(
                    "was_canonicalized"
                ):
                    canonicalization = product.raw_data["_canonicalization"]
                    if not json_output:
                        console = get_console()
                        console.print("\n[cyan]i Using canonical URL[/cyan]")
                        console.print(f"  [dim]Provided:[/dim]  {canonicalization['original_url']}")
                        console.print(
                            f"  [dim]Canonical:[/dim] {canonicalization['canonical_url']}\n"
                        )

                # Add/update tracked_pages entry (same as check-scheduled)
                # Use product.url (canonical URL) instead of single_url for database operations
                if product:
                    try:
                        tracked_url = product.url  # Use canonical URL for tracking
                        existing_page = db_manager.get_tracked_page(tracked_url)
                        if existing_page:
                            db_manager.update_last_checked(tracked_url, product.current_price)
                        else:
                            page_data = {
                                "url": tracked_url,
                                "provider": provider_name,
                                "enabled": True,
                                "last_checked": now_in_configured_tz(),
                                "last_price": product.current_price,
                            }
                            db_manager.add_tracked_page(page_data)

                        # Handle group association (priority: --group flag > config.yaml)
                        if resolved_group_name:
                            # Create group if doesn't exist and associate
                            associate_tracked_page_with_group(
                                tracked_url, resolved_group_name, db_manager
                            )
                        else:
                            # Fallback: Auto-associate with product groups from config
                            associated_groups = auto_associate_with_groups(tracked_url, db_manager)
                            if associated_groups:
                                logger.debug(
                                    f"Auto-associated URL with groups: {', '.join(associated_groups)}"
                                )

                    except Exception as e:
                        # Log foreign key constraint errors as debug (they don't affect tracking)
                        # NOTE: This is expected when updating pages that are already referenced in product groups
                        if "foreign key constraint" in str(e).lower():
                            logger.debug(
                                f"Foreign key constraint during page update for {single_url}: {e}"
                            )
                            logger.debug(
                                "This is expected behavior when a tracked page is already associated with a product group"
                            )
                        else:
                            # Silently log error to avoid disrupting user output
                            logger.error(f"Failed to add tracked_page for {single_url}: {e}")

            # Check if extraction failed
            if not product:
                error_msg = f"Failed to extract product data from: {single_url}"
                if json_output:
                    output_json_response(None, error_msg)
                    return
                else:
                    show_error("Failed to extract product data", details=f"URL: {single_url}")
                    raise click.Abort()

            # Output results
            if json_output:
                output_json_response(product, None)
            else:
                console = get_console()
                display_table_output(product, db_result_tracking, full, console)

    except click.Abort:
        # Already handled above
        raise
    except Exception as e:
        error_msg = str(e)
        if json_output:
            output_json_response(None, error_msg)
        else:
            show_error("Failed to track product", details=error_msg)
            raise click.Abort() from e


track = cast(click.Command, track)
