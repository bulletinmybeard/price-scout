import logging
from typing import cast

from chalkbox.components.padding import Padding
from chalkbox.components.section import Section
import click
from rich.table import Table as RichTable

from src.cli.helpers import get_console, get_db_url
from src.config import ConfigLoader
from src.database.db_manager import DatabaseManager
from src.price_tracker.comparator import PriceComparator
from src.price_tracker.group_sync import GroupSync
from src.providers import get_factory

console = get_console()


@click.group()
@click.pass_context
def groups(ctx: click.Context):
    """Manage product groups for price comparison."""
    debug = ctx.obj.get("debug", False)
    if not debug:
        # Production mode: only show warnings and errors
        logging.getLogger().setLevel(logging.WARNING)
        for logger_name in ["src", "config", "playwright", "urllib3", "asyncio"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


@groups.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def list_groups(verbose: bool):
    """List all product groups."""
    try:
        db_manager = DatabaseManager(get_db_url())
        all_groups = db_manager.get_all_groups()

        if not all_groups:
            console.print("\n[yellow]No product groups found.[/yellow]")
            console.print(
                "[dim]Create groups in config.yaml and run 'price-scout groups sync'[/dim]\n"
            )
            return

        console.print(
            f"\n[bold cyan]Product Groups[/bold cyan] ([dim]{len(all_groups)} total[/dim])\n"
        )

        if not verbose:
            # Simple table view
            table = RichTable(show_header=True, header_style="bold cyan", expand=False)
            table.add_column("Group Name", style="white", no_wrap=False)
            table.add_column("ID", justify="right", style="dim")
            table.add_column("Products", justify="right", style="cyan")
            table.add_column("Status", style="green")

            for group in all_groups:
                pages = db_manager.get_group_pages(group["name"])
                page_count = len(pages) if pages else 0
                status = "✓ Active" if group.get("enabled", True) else "○ Inactive"

                table.add_row(group["name"], str(group["group_id"]), str(page_count), status)

            console.print(table)
            console.print()

        else:
            # Verbose view with panels for each group
            for group in all_groups:
                pages = db_manager.get_group_pages(group["name"])
                page_count = len(pages) if pages else 0
                status = "✓ Active" if group.get("enabled", True) else "○ Inactive"

                # Build panel header subtitle
                subtitle = f"ID: {group['group_id']} | Products: {page_count} | Status: {status}"

                panel_content: RichTable | str
                if pages:
                    # Create table for pages
                    pages_table = RichTable(
                        show_header=True, header_style="bold", expand=True, show_edge=False
                    )
                    pages_table.add_column("Provider", style="yellow", no_wrap=True)
                    pages_table.add_column("URL", style="bright_blue", no_wrap=False)

                    for page in pages:
                        provider = page.get("provider", "unknown")
                        provider_display = provider.replace("_", " ").title()
                        # Truncate URL smartly
                        url = page["url"]
                        url_display = url if len(url) <= 70 else url[:67] + "..."

                        pages_table.add_row(provider_display, url_display)

                    panel_content = pages_table
                else:
                    panel_content = "[dim]No pages tracked in this group[/dim]"

                section = Section(
                    title=f"[bold]{group['name']}[/bold]",
                    footer=f"[dim]{subtitle}[/dim]",
                    border_style="cyan",
                )
                section.add(panel_content)
                console.print(section)
                console.print()

    except Exception as e:
        click.echo(f"  Error listing groups: {e}")
        raise click.Abort() from e


@groups.command("show")
@click.argument("group_name", type=str)
def show_group(group_name: str):
    """Show detailed information about a specific group."""
    try:
        db_manager = DatabaseManager(get_db_url())
        group = db_manager.get_group_by_name(group_name)

        if not group:
            console.print(f"\n[yellow]Group '{group_name}' not found[/yellow]\n")
            raise click.Abort()

        status = "✓ Active" if group.get("enabled", True) else "○ Inactive"
        subtitle_parts = [f"ID: {group['group_id']}", f"Status: {status}"]
        if group.get("description"):
            subtitle_parts.append(group["description"])
        subtitle = " | ".join(subtitle_parts)

        pages = db_manager.get_group_pages(group_name)

        panel_content: RichTable | str
        if pages:
            pages_table = RichTable(
                show_header=True, header_style="bold cyan", expand=True, show_edge=False
            )
            pages_table.add_column("Provider", style="yellow", no_wrap=True, width=15)
            pages_table.add_column("Product Name", style="white", no_wrap=False, width=40)
            pages_table.add_column("Latest Price", justify="right", style="green", width=12)

            comparison = db_manager.get_group_comparison(group_name)
            price_map = {}
            if comparison and comparison.get("providers"):
                for item in comparison["providers"]:
                    provider = item.get("provider", "unknown")
                    price_map[provider] = {
                        "price": item.get("current_price"),
                        "available": item.get("is_available"),
                    }

            for page in pages:
                provider = page.get("provider", "unknown")
                provider_display = provider.replace("_", " ").title()

                product_name = page.get("product_name", "")
                if not product_name:
                    url_parts = page["url"].rstrip("/").split("/")
                    product_name = url_parts[-1] if url_parts else "Unknown"

                if len(product_name) > 40:
                    product_name = product_name[:37] + "..."

                price_info = price_map.get(provider, {})
                price_str = f"EUR {price_info['price']:.2f}" if price_info.get("price") else "N/A"

                pages_table.add_row(provider_display, product_name, price_str)

            panel_content = pages_table
        else:
            panel_content = "[dim]No pages tracked in this group[/dim]"

        section = Section(
            title=f"[bold cyan]{group['name']}[/bold cyan]",
            footer=f"[dim]{subtitle}[/dim]",
            border_style="cyan",
        )
        section.add(panel_content)

        console.print("\n")
        console.print(section)
        console.print()

    except Exception as e:
        click.echo(f"  Error showing group: {e}")
        raise click.Abort() from e


@groups.command("compare")
@click.argument("group_name", type=str)
@click.option("--days", "-d", type=int, default=30, help="Number of days for price history")
def compare_group(group_name: str, days: int):
    """Compare prices across all products in a group."""
    try:
        db_manager = DatabaseManager(get_db_url())
        comparator = PriceComparator(db_manager)

        group = db_manager.get_group_by_name(group_name)
        if not group:
            click.echo(f"  Group '{group_name}' not found")
            raise click.Abort()

        comparison = comparator.compare_group(group_name)

        if not comparison:
            click.echo("No price data available for this group")
            return

        providers = comparison.get("providers", [])
        if not providers:
            click.echo("No price data available for this group")
            return

        group_header = Padding.horizontal(f"\nPrice Comparison: {group['name']}\n", amount=2)
        console.print(group_header)

        if days > 0:
            history_header = Padding.horizontal(f"Price History (last {days} days):", amount=2)
            console.print(history_header)
            history_summary = comparator.get_group_price_history(group_name, days)

            if history_summary:
                factory = get_factory()
                provider_display_names = {}
                for provider_slug in factory.list_providers():
                    try:
                        config: dict = factory.config.get(provider_slug, {})  # type: ignore[assignment]
                        display_name = config.get(
                            "display_name", provider_slug.replace("_", " ").title()
                        )
                        provider_display_names[provider_slug] = display_name
                    except Exception:
                        provider_display_names[provider_slug] = provider_slug.replace(
                            "_", " "
                        ).title()

                # Aggregate by provider (history has one row per day per provider)
                provider_stats = {}
                for item in history_summary:
                    provider = item.get("provider", "unknown")
                    url = item.get("url", "")
                    product_name = item.get("product_name", "")
                    latest_scraped = item.get("latest_scraped_at")

                    if provider not in provider_stats:
                        provider_stats[provider] = {
                            "product_name": product_name,
                            "url": url,
                            "min_prices": [],
                            "max_prices": [],
                            "avg_prices": [],
                            "latest_scraped": latest_scraped,
                            "current_prices": [],  # Track all prices to get the most recent
                        }

                    if item.get("min_price"):
                        provider_stats[provider]["min_prices"].append(item["min_price"])
                    if item.get("max_price"):
                        provider_stats[provider]["max_prices"].append(item["max_price"])
                    if item.get("avg_price"):
                        provider_stats[provider]["avg_prices"].append(item["avg_price"])
                        # The most recent avg_price is the current price (since ordered by date DESC)
                        if not provider_stats[provider]["current_prices"]:
                            provider_stats[provider]["current_prices"].append(item["avg_price"])

                    if latest_scraped and (
                        not provider_stats[provider]["latest_scraped"]
                        or latest_scraped > provider_stats[provider]["latest_scraped"]
                    ):
                        provider_stats[provider]["latest_scraped"] = latest_scraped

                current_prices = {}
                for item in providers:
                    current_prices[item["provider"]] = item.get("current_price")

                table = RichTable(show_header=True, header_style="bold cyan", expand=True)
                table.add_column("Deal", justify="center", style="yellow", no_wrap=True)
                table.add_column("Provider", style="yellow", no_wrap=True)
                table.add_column(
                    "Product Name", style="white", no_wrap=False, overflow="ellipsis", max_width=40
                )
                table.add_column("Product URL", style="bright_blue", no_wrap=False)
                table.add_column("Current", justify="right", style="bright_green")
                table.add_column("Min", justify="right", style="green")
                table.add_column("Max", justify="right", style="red")
                table.add_column("Avg", justify="right", style="cyan")
                table.add_column("Last Update", justify="right", style="dim")

                # Find he cheapest price for severity calculation
                valid_prices = [
                    price for p in provider_stats if (price := current_prices.get(p)) is not None
                ]
                cheapest_price = min(valid_prices) if valid_prices else None

                # Sort providers by current price (cheapest first)
                sorted_providers = sorted(
                    provider_stats.items(), key=lambda x: current_prices.get(x[0]) or float("inf")
                )

                for provider, stats in sorted_providers:
                    min_price = min(stats["min_prices"]) if stats["min_prices"] else None
                    max_price = max(stats["max_prices"]) if stats["max_prices"] else None
                    avg_price = (
                        sum(stats["avg_prices"]) / len(stats["avg_prices"])
                        if stats["avg_prices"]
                        else None
                    )
                    current_price = current_prices.get(provider)

                    if min_price and max_price and avg_price:
                        provider_name = provider_display_names.get(
                            provider, provider.replace("_", " ").title()
                        )

                        product_name_display = (
                            stats["product_name"][:37] + "..."
                            if len(stats["product_name"]) > 40
                            else stats["product_name"]
                        )

                        last_update = ""
                        if stats["latest_scraped"]:
                            from datetime import datetime

                            if isinstance(stats["latest_scraped"], str):
                                dt = datetime.fromisoformat(
                                    stats["latest_scraped"].replace("Z", "+00:00")
                                )
                            else:
                                dt = stats["latest_scraped"]
                            last_update = dt.strftime("%Y-%m-%d %H:%M")

                        # Create clickable URL (format: [link=URL]display_text[/link])
                        url_display = f"[link={stats['url']}]{stats['url']}[/link]"

                        # Check if price has changed (min == max == avg == current)
                        price_unchanged = (
                            current_price
                            and abs(min_price - current_price) < 0.01
                            and abs(max_price - current_price) < 0.01
                            and abs(avg_price - current_price) < 0.01
                        )

                        if price_unchanged:
                            min_display = "-"
                            max_display = "-"
                            avg_display = "-"
                        else:
                            min_display = f"€{min_price:.2f}"
                            max_display = f"€{max_price:.2f}"
                            avg_display = f"€{avg_price:.2f}"

                        # Calculate deal indicator (only for the Deal column!)
                        deal_indicator = ""
                        if (
                            current_price
                            and cheapest_price
                            and abs(current_price - cheapest_price) < 0.01
                        ):
                            deal_indicator = "*"

                        table.add_row(
                            deal_indicator,
                            provider_name,
                            product_name_display,
                            url_display,
                            f"€{current_price:.2f}" if current_price else "N/A",
                            min_display,
                            max_display,
                            avg_display,
                            last_update,
                        )

                padded_table = Padding.symmetric(table, vertical=1, horizontal=2)
                console.print(padded_table)

        click.echo()

    except Exception as e:
        click.echo(f"  Error comparing prices: {e}")
        raise click.Abort() from e


@groups.command("sync")
@click.option("--dry-run", is_flag=True, help="Show what would be synced without making changes")
@click.pass_context
def sync_groups(ctx: click.Context, dry_run: bool):
    """Sync product groups from config to database (optional)."""
    try:
        config_file = ctx.obj.get("config_file")
        config_name = config_file if config_file else "config.yaml"

        loader = ConfigLoader(config_file) if config_file else ConfigLoader()
        typed_config = loader.load_typed()

        # Write mode needed to sync groups
        db_manager = DatabaseManager(typed_config.database.url, read_only=False)

        sync = GroupSync(db_manager, typed_config)

        changes = sync.sync_groups(dry_run=dry_run)

        content_lines = []

        if dry_run:
            content_lines.append("[yellow]Dry run mode - no changes will be made[/yellow]\n")

        content_lines.append(f"✓ Synced from [cyan]{config_name}[/cyan]\n")

        if changes["created"]:
            content_lines.append(f"[green]Created Groups ({len(changes['created'])})[/green]")
            for group_name in changes["created"]:
                content_lines.append(f"  • {group_name}")
            content_lines.append("")

        if changes["updated"]:
            content_lines.append(f"[green]Updated Groups ({len(changes['updated'])})[/green]")
            for group_name in changes["updated"]:
                content_lines.append(f"  • {group_name}")
            content_lines.append("")

        if changes["deactivated"]:
            content_lines.append(
                f"[yellow]Deactivated Groups ({len(changes['deactivated'])})[/yellow]"
            )
            for group_name in changes["deactivated"]:
                content_lines.append(f"  • {group_name}")
            content_lines.append("")

        if not any([changes["created"], changes["updated"], changes["deactivated"]]):
            content_lines.append("[green]✓ All groups are already in sync[/green]")

        if dry_run:
            content_lines.append("\nRun without --dry-run to apply these changes")

        # Create and print section
        section = Section(title="[bold cyan]Product Group Sync[/bold cyan]", border_style="cyan")
        section.add("\n".join(content_lines))
        console.print("\n")
        console.print(section)
        console.print()

    except Exception as e:
        click.echo(f"  Error syncing groups: {e}")
        raise click.Abort() from e


groups = cast(click.Group, groups)
