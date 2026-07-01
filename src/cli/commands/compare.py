from itertools import groupby
from typing import cast

from chalkbox.logging.bridge import get_logger
import click
from rich import box
from rich.panel import Panel
from rich.table import Table as RichTable

from src.cli.helpers import detect_provider_from_url, get_console, get_db_url
from src.database.db_manager import DatabaseManager
from src.price_tracker.comparator import PriceComparator
from src.price_tracker.tracker import PriceTracker
from src.providers.provider_factory import get_factory

console = get_console()
logger = get_logger(__name__)


@click.group()
@click.pass_context
def compare(_ctx: click.Context):
    """Compare prices across providers, groups, or products."""
    pass


@compare.command("groups")
@click.option(
    "--name",
    "-n",
    "group_names",
    multiple=True,
    required=True,
    help="Product group name (repeatable for multiple groups)",
)
@click.option(
    "--refresh", is_flag=True, help="Refresh prices before comparison (scrapes latest data)"
)
@click.pass_context
def compare_groups(_ctx: click.Context, group_names: tuple[str, ...], refresh: bool):
    """
    Compare total basket costs across multiple product groups.

    Examples:

        # Compare basket across 2 groups
        price-scout compare groups --name "Coffee" --name "Milk"

        # Use short flag
        price-scout compare groups -n "Weekly Groceries" -n "Monthly Essentials"

        # Refresh prices first, then compare
        price-scout compare groups --name "Coffee" --name "Milk" --refresh
    """
    try:
        group_list = list(group_names)

        if len(group_list) < 2:
            click.echo("Error: At least 2 product groups required for basket comparison")
            raise click.Abort()

        db_manager = DatabaseManager(get_db_url())

        if refresh:
            click.echo(f"Refreshing prices for {len(group_list)} groups...")

            factory = get_factory()
            tracker = PriceTracker(db_manager)

            total_success = 0
            total_failed = 0

            # Refresh each group sequentially
            for group_name in group_list:
                click.echo(f"  Refreshing group: {group_name}...")
                success, failed = _refresh_group_products(group_name, db_manager, tracker, factory)
                total_success += success
                total_failed += failed
                click.echo(f"    {success} succeeded, {failed} failed")

            click.echo(
                f"\nRefresh complete: {total_success} products updated, {total_failed} failed\n"
            )
        comparator = PriceComparator(db_manager)

        result = comparator.compare_baskets(group_names=group_list)

        if result["missing_groups"]:
            click.echo(f"Warning: Groups not found: {', '.join(result['missing_groups'])}\n")

        if not result["providers"]:
            click.echo("No data found for specified groups")
            raise click.Abort()

        _display_provider_totals(
            result["providers"], result["statistics"], result.get("products", [])
        )
        click.echo()
        _display_category_subtotals(result["categories"])
        click.echo()
        _display_product_breakdown(result["products"])
        click.echo()
        _display_basket_statistics(result["statistics"])

    except ValueError as e:
        click.echo(f"Error: {e}")
        raise click.Abort() from e
    except Exception as e:
        click.echo(f"Error comparing baskets: {e}")
        raise click.Abort() from e


def _provider_currencies(products: list[dict]) -> dict[str, str]:
    currencies: dict[str, str] = {}
    for product in products:
        provider = product.get("provider")
        if provider and provider not in currencies:
            currencies[provider] = product.get("currency") or "EUR"
    return currencies


def _display_provider_totals(providers: list[dict], stats: dict, products: list[dict]):
    table = RichTable(
        title="Basket Comparison - Provider Totals",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Provider", style="cyan", no_wrap=True)
    table.add_column("Total Cost", justify="right", style="green")
    table.add_column("Products", justify="right")
    table.add_column("Available", justify="right")
    table.add_column("Unavailable", justify="right", style="red")
    table.add_column("Promotions", justify="right", style="yellow")
    table.add_column("Savings", justify="right", style="magenta")

    currencies = _provider_currencies(products)

    # Sort by total cost (cheapest first)
    sorted_providers = sorted(providers, key=lambda x: x["total_cost"])
    cheapest = sorted_providers[0]

    for provider in sorted_providers:
        currency = currencies.get(provider["provider"], "EUR")
        is_cheapest = provider["provider"] == cheapest["provider"]
        savings = provider["total_cost"] - cheapest["total_cost"]
        unavailable_count = provider["product_count"] - provider["available_count"]

        # Highlight cheapest provider
        name_style = "bold green" if is_cheapest else "cyan"
        cost_style = "bold green" if is_cheapest else "white"

        table.add_row(
            f"[{name_style}]{provider['provider']}[/{name_style}]"
            + (" [bold green]BEST[/bold green]" if is_cheapest else ""),
            f"[{cost_style}]{currency}{provider['total_cost']:.2f}[/{cost_style}]",
            str(provider["product_count"]),
            f"{provider['available_count']}/{provider['product_count']}",
            str(unavailable_count) if unavailable_count > 0 else "-",
            str(provider.get("promotion_count", 0)),
            f"+{currency}{savings:.2f}" if savings > 0 else f"{currency}0.00",
        )

    console.print(table)

    # Winner summary
    if len(providers) > 1 and stats and stats.get("price_ranges"):
        diff = stats["price_ranges"]["difference"]
        diff_pct = stats["price_ranges"]["difference_pct"]
        winner_currency = currencies.get(cheapest["provider"], "EUR")
        click.echo(
            f"\n{cheapest['provider']} is cheapest: "
            f"{winner_currency}{diff:.2f} ({diff_pct:.1f}%) savings vs most expensive"
        )

    total_unavailable = sum(p["product_count"] - p["available_count"] for p in providers)
    if total_unavailable > 0:
        click.echo(
            f"\nNote: Total cost excludes {total_unavailable} unavailable product(s) "
            f"across all providers"
        )


def _display_category_subtotals(categories: list[dict]):
    if not categories:
        return

    table = RichTable(
        title="Category Breakdown",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Category", style="cyan")
    table.add_column("Provider", style="white")
    table.add_column("Subtotal", justify="right", style="green")
    table.add_column("Products", justify="right")

    for cat in categories:
        table.add_row(
            cat["category"],
            cat["provider"],
            f"EUR{cat['subtotal']:.2f}",
            str(cat["count"]),
        )

    console.print(table)


def _display_product_breakdown(products: list[dict]):
    if not products:
        return

    table = RichTable(
        title="Product Breakdown",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Group", style="cyan", no_wrap=True)
    table.add_column("Product", style="white", overflow="fold")
    table.add_column("Provider", style="yellow", no_wrap=True)
    table.add_column("Price", justify="right", style="green")
    table.add_column("Status", justify="center")

    # Group by provider then category
    sorted_products = sorted(
        products, key=lambda x: (x["provider"], x.get("category", ""), x["group_name"])
    )

    for provider, provider_products in groupby(sorted_products, key=lambda x: x["provider"]):
        # Add provider separator
        table.add_row("", f"[bold]{provider.upper()}[/bold]", "", "", "")

        for product in provider_products:
            status_icons = []
            if product.get("is_promotion"):
                status_icons.append("PROMO")
            if not product.get("is_available"):
                status_icons.append("OUT")  # Mark unavailable
            status = " ".join(status_icons) if status_icons else "OK"

            # Format product name with length limit
            product_name = product["name"]
            if len(product_name) > 50:
                product_name = product_name[:50] + "..."

            table.add_row(
                product["group_name"],
                product_name,
                product["provider"],
                f"EUR{product['price']:.2f}",
                status,
            )

    console.print(table)


def _display_basket_statistics(stats: dict):
    if not stats or not stats.get("price_ranges"):
        return

    panel_content = f"""
[cyan]Groups Compared:[/cyan] {stats["total_groups"]}
[cyan]Products per Provider:[/cyan] {stats["total_products"]}
[cyan]Providers Compared:[/cyan] {stats["providers_compared"]}

[yellow]Promotions:[/yellow]
{_format_provider_counts(stats.get("promotion_count", {}))}

[red]Unavailable:[/red]
{_format_provider_counts(stats.get("unavailable_count", {}))}

[green]Price Range:[/green]
  Cheapest: {stats["price_ranges"]["min"]["provider"]} (EUR{stats["price_ranges"]["min"]["price"]:.2f})
  Most Expensive: {stats["price_ranges"]["max"]["provider"]} (EUR{stats["price_ranges"]["max"]["price"]:.2f})
  Difference: EUR{stats["price_ranges"]["difference"]:.2f} ({stats["price_ranges"]["difference_pct"]:.1f}%)
    """

    console.print(Panel(panel_content, title="Statistics", border_style="cyan"))


def _format_provider_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "  None"
    return "\n".join(f"  {provider}: {count}" for provider, count in counts.items())


def _refresh_group_products(group_name, db_manager, tracker, factory):
    group = db_manager.get_group_by_name(group_name)
    if not group:
        return (0, 0)

    pages = db_manager.get_group_pages(group_name)
    if not pages:
        return (0, 0)

    success_count = 0
    failed_count = 0

    # Refresh each URL sequentially (simpler than threading for groups)
    for page in pages:
        url = page["url"]
        try:
            provider_name, _ = detect_provider_from_url(url, factory)
            if not provider_name:
                failed_count += 1
                continue

            tracker.track_product_url(url, provider_name, track_to_db=True)
            success_count += 1

        except Exception as e:
            logger.debug(f"Failed to refresh {url}: {e}")
            failed_count += 1

    return (success_count, failed_count)


compare = cast(click.Group, compare)
