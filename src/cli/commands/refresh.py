from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import cast

import click

from src.cli.helpers import detect_provider_from_url, get_db_url
from src.database.db_manager import DatabaseManager
from src.price_tracker.tracker import PriceTracker
from src.providers import get_factory


@click.command()
@click.option(
    "--providers",
    "-p",
    help="Comma-separated list of providers to refresh (default: all)",
)
@click.option(
    "--group",
    "-g",
    help="Refresh all products in a specific product group",
)
@click.option(
    "--url",
    "-u",
    help="Refresh specific product URL only",
)
@click.pass_context
def refresh(ctx: click.Context, providers, group, url):
    """
    Refresh prices for tracked products.

    Scrapes current prices for tracked products and updates the database.
    You can refresh all products, filter by provider, refresh a specific group,
    or refresh a single URL.

    Examples:
        # Refresh all tracked products
        price-scout refresh

        # Refresh specific providers only
        price-scout refresh --providers store_a,store_b

        # Refresh all products in a group
        price-scout refresh --group "Pedigree Adult Maaltijdzakjes"

        # Refresh single product
        price-scout refresh --url "https://www.webshop-a/products/..."
    """
    # Configure logging based on debug flag
    debug = ctx.obj.get("debug", False)
    if not debug:
        # Production mode: only show warnings and errors
        logging.getLogger().setLevel(logging.WARNING)
        for logger_name in ["src", "config", "playwright", "urllib3", "asyncio"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

    db_manager = DatabaseManager(get_db_url(), read_only=False)
    tracker = PriceTracker(db_manager)
    provider_config_override = ctx.obj.get("provider_config")
    factory = get_factory(provider_config=provider_config_override)

    urls_to_refresh = []

    if url:
        click.echo(f"Refreshing single product: {url}\n")
        urls_to_refresh = [url]

    elif group:
        click.echo(f"Refreshing product group: {group}\n")

        group_obj = db_manager.get_group_by_name(group)
        if not group_obj:
            click.echo(f"✗ Group '{group}' does not exist.")
            raise click.Abort()

        group_pages = db_manager.get_group_pages(group)
        if not group_pages:
            click.echo(f"✗ No products found in group '{group}'.")
            raise click.Abort()
        urls_to_refresh = [page["url"] for page in group_pages]
        click.echo(f"Found {len(urls_to_refresh)} product(s) in group.\n")

    else:
        click.echo("Refreshing all tracked products...\n")
        tracked_pages = db_manager.get_all_tracked_pages()

        # Filter by provider (if specified)
        if providers:
            factory = get_factory()
            available_providers = factory.list_providers()

            provider_list = [p.strip() for p in providers.split(",")]

            # Validate providers exist
            invalid_providers = [p for p in provider_list if p not in available_providers]
            if invalid_providers:
                click.echo(f"✗ Invalid provider(s): {', '.join(invalid_providers)}")
                click.echo(f"Available providers: {', '.join(sorted(available_providers))}")
                raise click.Abort()

            urls_to_refresh = [
                page["url"]
                for page in tracked_pages
                if page.get("enabled") and page.get("provider") in provider_list
            ]
            click.echo(f"Filtering by providers: {', '.join(provider_list)}")
        else:
            urls_to_refresh = [page["url"] for page in tracked_pages if page.get("enabled")]

        click.echo(f"Found {len(urls_to_refresh)} tracked product(s).\n")

    if not urls_to_refresh:
        click.echo("✗ No products to refresh.")
        return

    stats = {"success": 0, "failed": 0, "total": len(urls_to_refresh)}

    click.echo("Refreshing prices...\n")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for url_item in urls_to_refresh:
            provider_name, _ = detect_provider_from_url(url_item, factory)
            if not provider_name:
                click.echo(f"✗ Could not detect provider for: {url_item}")
                stats["failed"] += 1
                continue

            future = executor.submit(
                _refresh_single_url, url_item, provider_name, tracker, db_manager
            )
            futures[future] = url_item

        for future in as_completed(futures):
            url_item = futures[future]
            try:
                success = future.result()
                if success:
                    stats["success"] += 1
                    click.echo(f"✓ Refreshed: {url_item[:60]}...")
                else:
                    stats["failed"] += 1
                    click.echo(f"✗ Failed: {url_item[:60]}...")
            except Exception as e:
                stats["failed"] += 1
                click.echo(f"✗ Error for {url_item[:60]}...: {e}")

    click.echo(f"\n{'=' * 60}")
    click.echo("Refresh Statistics:")
    click.echo(f"  Total:   {stats['total']}")
    click.echo(f"  Success: {stats['success']}")
    click.echo(f"  Failed:  {stats['failed']}")
    click.echo(f"{'=' * 60}")


def _refresh_single_url(url: str, provider_name: str, tracker, db_manager) -> bool:
    """Refresh a single URL and return success status."""
    try:
        product, _db_result = tracker.track_product_url(url, provider_name, track_to_db=True)
        return product is not None
    except Exception:
        return False


refresh = cast(click.Command, refresh)
