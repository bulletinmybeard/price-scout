import json
from typing import Any

import click
from rich.table import Table as RichTable

from src.cli.helpers import get_console, get_db_url
from src.database.db_manager import DatabaseManager

console = get_console()


def _format_price(price: float | None, currency: str | None) -> str:
    if price is None:
        return "n/a"
    code = currency or "EUR"
    return f"{code} {price:.2f}"


@click.command("history")
@click.argument("url")
@click.option("--days", "-d", type=int, default=30, show_default=True, help="How many days back")
@click.option("--json", "as_json", is_flag=True, help="Output snapshots as JSON")
@click.pass_context
def history(ctx: click.Context, url: str, days: int, as_json: bool) -> None:
    """Show stored price history for a product URL.

    Example:
        price-scout history "https://www.example.com/product/1"
    """
    config_file = ctx.obj.get("config_file") if ctx.obj else None
    db_manager = DatabaseManager(get_db_url(config_file), read_only=True)
    try:
        snapshots = db_manager.get_snapshot_history(url, days=days)
    finally:
        db_manager.close()

    if as_json:
        click.echo(json.dumps(snapshots, indent=2, default=str))
        return

    if not snapshots:
        click.echo(f"No price history for {url} in the last {days} days.")
        return

    latest: dict[str, Any] = snapshots[0]
    name = latest.get("name") or url
    provider = latest.get("provider") or "unknown"
    click.echo(f"{name} ({provider})")

    table = RichTable(show_header=True, header_style="bold")
    table.add_column("Scraped")
    table.add_column("Price", justify="right")
    table.add_column("Available")
    table.add_column("Promotion")

    for snapshot in snapshots:
        scraped = snapshot.get("scraped_at")
        scraped_text = str(scraped)[:19] if scraped else "n/a"
        available = "yes" if snapshot.get("availability") else "no"
        if snapshot.get("is_marketplace_only"):
            promotion = "marketplace"
        elif snapshot.get("has_promotion"):
            discount = snapshot.get("discount_percentage")
            promotion = f"{discount:.0f}%" if isinstance(discount, (int, float)) else "yes"
        else:
            promotion = "no"
        table.add_row(
            scraped_text,
            _format_price(snapshot.get("current_price"), snapshot.get("currency")),
            available,
            promotion,
        )

    console.print(table)
