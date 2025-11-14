import json
from typing import Any

from chalkbox import Table

from src.cli.helpers import extract_amount_from_name
from src.providers.base_product import BaseProduct
from src.utils.product_parser import normalize_unit_code


def _get_product_amount(snapshot: dict[str, Any]) -> str:
    """
    Extract product amount from snapshot.

    Priority:
    1. Structured fields (amount_value + amount_unit) with pack info
    2. Legacy combined fields (weight, volume, dimensions)
    3. Extract from name (fallback)
    4. N/A
    """
    # Priority 1: Use structured amount fields (new)
    amount_value = snapshot.get("amount_value")
    amount_unit = snapshot.get("amount_unit")
    pack_quantity = snapshot.get("pack_quantity", 1)

    if amount_value is not None and amount_unit:
        # Format with pack quantity if multi-pack
        if pack_quantity > 1:
            return f"{int(pack_quantity)}x {amount_value} {amount_unit}"
        else:
            # Single item
            return f"{amount_value} {amount_unit}" if amount_value else amount_unit

    # Priority 2: Legacy combined fields (normalize UN/CEFACT codes)
    weight = snapshot.get("weight")
    volume = snapshot.get("volume")
    dimensions = snapshot.get("dimensions")

    # Normalize UN/CEFACT codes in legacy fields
    if weight:
        # Replace UN/CEFACT codes with normalized units
        import re

        for code in ["KGM", "GRM", "LTR", "MLT", "CMT"]:
            if code in weight:
                normalized = normalize_unit_code(code)
                weight = re.sub(r"\b" + code + r"\b", normalized, weight, flags=re.IGNORECASE)
        return weight

    if volume:
        import re

        for code in ["LTR", "MLT", "CLT"]:
            if code in volume:
                normalized = normalize_unit_code(code)
                volume = re.sub(r"\b" + code + r"\b", normalized, volume, flags=re.IGNORECASE)
        return volume

    if dimensions:
        return dimensions

    # Priority 3: Extract from name (fallback)
    name = snapshot.get("name", "")
    extracted = extract_amount_from_name(name)
    return extracted if extracted else "N/A"


def _format_price(price: float | None, currency: str = "EUR") -> str:
    """Format price with currency."""
    return f"{currency} {price:.2f}" if price else "N/A"


def _format_boolean(value: bool, true_str: str = "✓ Yes", false_str: str = "✗ No") -> str:
    """Format boolean value with custom strings."""
    return true_str if value else false_str


def _format_promotion(has_promotion: bool, discount_pct: float | None = None) -> str:
    """Format promotion status with optional discount percentage."""
    if has_promotion and discount_pct:
        return f"✓ Yes {discount_pct:.0f}%"
    elif has_promotion:
        return "✓ Yes"
    else:
        return "✗ No"


def _truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length with suffix."""
    return text[: max_length - len(suffix)] + suffix if len(text) > max_length else text


def _format_timestamp(timestamp: Any) -> str:
    """Format timestamp to string, truncating to 19 characters (YYYY-MM-DD HH:MM:SS)."""
    if timestamp == "N/A" or timestamp is None:
        return "N/A"
    return str(timestamp)[:19]


def _build_price_comparison_object(
    provider: str, name: str, price: float, currency: str, url: str
) -> dict[str, Any]:
    """Build standardized price comparison object."""
    return {
        "provider": provider,
        "product": name,
        "price": price,
        "currency": currency,
        "url": url,
    }


def display_table_output(product: BaseProduct, db_result: dict | None, show_full: bool, console):
    """Display product information in ChalkBox table.

    Note: 2-column table kept narrow for better readability.
    """
    table = Table(title="Product Information", headers=["Field", "Value"])

    all_fields = [
        ("name", "Product Name"),
        ("url", "Product URL"),
        ("brand", "Brand"),
        ("manufacturer", "Manufacturer"),
        ("category", "Category"),
        ("tags", "Tags"),
        ("current_price", "Current Price"),
        ("original_price", "Original Price"),
        ("currency", "Currency"),
        ("price_per_unit", "Price/Unit"),
        ("has_promotion", "Has Promotion"),
        ("discount_percentage", "Discount %"),
        ("promotion_text", "Promotion Text"),
        ("promotion_ends_at", "Promotion Ends At"),
        ("availability", "Available"),
        ("availability_text", "Availability Status"),
        ("stock_quantity", "Stock Quantity"),
        ("max_order_quantity", "Max Order Quantity"),
        ("sku", "SKU"),
        ("gtin", "GTIN/EAN"),
        ("description", "Description"),
        ("short_description", "Short Description"),
        ("features", "Features"),
        ("image", "Image URL"),
        ("images", "All Images"),
        ("rating", "Rating"),
        ("rating_count", "Rating Count"),
        ("review_count", "Review Count"),
        ("weight", "Weight"),
        ("dimensions", "Dimensions"),
        ("volume", "Volume"),
        ("color", "Color"),
        ("size", "Size"),
        ("ingredients", "Ingredients"),
        ("nutrition_info", "Nutrition Info"),
        ("allergens", "Allergens"),
        ("dietary_info", "Dietary Info"),
        ("shipping_cost", "Shipping Cost"),
        ("free_shipping", "Free Shipping"),
        ("delivery_time", "Delivery Time"),
        ("provider", "Provider"),
        ("extraction_method", "Extraction Method"),
        ("extracted_at", "Extracted At"),
    ]

    key_field_names = {
        "name",
        "url",
        "brand",
        "category",
        "current_price",
        "original_price",
        "currency",
        "price_per_unit",
        "has_promotion",
        "discount_percentage",
        "availability",
        "availability_text",
        "stock_quantity",
        "sku",
        "gtin",
        "weight",
        "image",
        "provider",
        "extraction_method",
        "extracted_at",
    }

    key_fields = [field for field in all_fields if field[0] in key_field_names]

    fields_to_display = all_fields if show_full else key_fields

    for field_key, field_label in fields_to_display:
        value = getattr(product, field_key, None)

        if value or value is False or value == 0:
            if field_key in ["has_promotion", "availability", "free_shipping"]:
                display_value = _format_boolean(value)
            elif field_key == "discount_percentage" and value:
                display_value = f"{value:.1f}%"
            elif field_key in ["current_price", "original_price", "shipping_cost"] and value:
                display_value = str(value)
            elif field_key == "category" and isinstance(value, list):
                display_value = ", ".join(value) if value else ""
            elif field_key == "description" and len(str(value)) > 100:
                display_value = str(value)[:100] + "..."
            elif field_key in ["url", "image"]:
                # Make URLs clickable using Rich markup syntax with truncation
                if value:
                    url_str = str(value)
                    display_text = url_str[:60] + "..." if len(url_str) > 60 else url_str
                    display_value = f"[link={value}]{display_text}[/link]"
                else:
                    display_value = ""
            elif field_key == "images" and isinstance(value, list):
                if value:
                    clickable_images = []
                    for img in value:
                        if img:
                            img_str = str(img)
                            display_text = img_str[:60] + "..." if len(img_str) > 60 else img_str
                            clickable_images.append(f"[link={img}]{display_text}[/link]")
                    display_value = "\n".join(clickable_images)
                else:
                    display_value = ""
            elif field_key == "extracted_at":
                display_value = value.strftime("%Y-%m-%d %H:%M:%S") if value else ""
            elif field_key == "promotion_ends_at":
                display_value = value.isoformat() if value else ""
            elif isinstance(value, list):
                display_value = ", ".join(str(v) for v in value) if value else ""
            elif isinstance(value, dict):
                display_value = json.dumps(value, indent=2)
            else:
                display_value = str(value) if value != "" else ""

            if display_value:
                table.add_row(field_label, display_value)

    console.print(table)

    if db_result:
        console.print("\n✓ Product tracked to database")
        console.print(f"  Snapshot ID: {db_result['snapshot_id']}")
        console.print(f"  Provider: {db_result['provider']}")
        console.print(f"  Price: {db_result['currency']} {db_result['price']}")
        console.print(f"  Scraped at: {db_result['scraped_at'].strftime('%Y-%m-%d %H:%M:%S')}")


def output_json_response(product: BaseProduct | None, error: str | None):
    """Output JSON response with status/data/error schema."""
    response: dict[str, Any]
    if error:
        response = {"status": "error", "data": None, "error": error}
    elif product:
        response = {"status": "success", "data": product.to_dict(), "error": None}
    else:
        response = {"status": "error", "data": None, "error": "Unknown error occurred"}

    print(json.dumps(response, indent=2, ensure_ascii=False))


def output_multi_json_response(results: list[tuple[str, str, Any]], error: str | None = None):
    """Output JSON response for multiple URLs with wrapped structure."""
    if error:
        error_response: dict[str, Any] = {"status": "error", "error": error, "products": []}
        print(json.dumps(error_response, indent=2, ensure_ascii=False))
        return

    products = []
    metadata = {"cached": 0, "scraped": 0, "errors": 0}

    cheapest = None
    cheapest_price = float("inf")
    most_expensive = None
    most_expensive_price = float("-inf")
    providers = set()
    prices = []

    for item in results:
        # Handle both 3-value (cached) and 4-value (scraped/error) tuples
        if len(item) == 4:
            source, url, data, elapsed = item
        else:
            source, url, data = item
            elapsed = 0  # Cached results have no elapsed time

        if source == "error":
            products.append(
                {
                    "source": "error",
                    "url": url,
                    "error": str(data),
                    "data": None,
                    "elapsed_seconds": round(elapsed, 2),
                }
            )
            metadata["errors"] += 1
        elif source == "cached":
            products.append({"source": "cached", "url": url, "data": data, "elapsed_seconds": 0})
            metadata["cached"] += 1

            # Track comparison data from cached snapshot
            if data:
                provider = data.get("provider", "unknown")
                providers.add(provider)
                price = data.get("current_price")
                if price:
                    prices.append(price)
                    if price < cheapest_price:
                        cheapest_price = price
                        cheapest = _build_price_comparison_object(
                            provider=provider,
                            name=data.get("name", "N/A"),
                            price=price,
                            currency=data.get("currency", "EUR"),
                            url=url,
                        )
                    if price > most_expensive_price:
                        most_expensive_price = price
                        most_expensive = _build_price_comparison_object(
                            provider=provider,
                            name=data.get("name", "N/A"),
                            price=price,
                            currency=data.get("currency", "EUR"),
                            url=url,
                        )
        elif source == "scraped":
            product_dict = data.to_dict() if data else None
            products.append(
                {
                    "source": "scraped",
                    "url": url,
                    "data": product_dict,
                    "elapsed_seconds": round(elapsed, 2),
                }
            )
            metadata["scraped"] += 1

            # Track comparison data from scraped product
            if product_dict:
                provider = product_dict.get("provider", "unknown")
                providers.add(provider)
                price = product_dict.get("current_price")
                if price:
                    prices.append(price)
                    if price < cheapest_price:
                        cheapest_price = price
                        cheapest = _build_price_comparison_object(
                            provider=provider,
                            name=product_dict.get("name", "N/A"),
                            price=price,
                            currency=product_dict.get("currency", "EUR"),
                            url=url,
                        )
                    if price > most_expensive_price:
                        most_expensive_price = price
                        most_expensive = _build_price_comparison_object(
                            provider=provider,
                            name=product_dict.get("name", "N/A"),
                            price=price,
                            currency=product_dict.get("currency", "EUR"),
                            url=url,
                        )

    comparison_summary: dict[str, Any] | None = None
    if len(results) > 1 and prices:  # Only add comparison for multi-URL with prices
        price_range: dict[str, Any] | None = (
            {
                "min": min(prices) if prices else None,
                "max": max(prices) if prices else None,
                "average": sum(prices) / len(prices) if prices else None,
                "currency": cheapest.get("currency", "EUR") if cheapest else "EUR",
            }
            if prices
            else None
        )
        comparison_summary = {
            "total_products": len(products),
            "providers": sorted(providers),
            "cheapest": cheapest,
            "most_expensive": most_expensive,
            "price_range": price_range,
        }

    response: dict[str, Any] = {
        "status": "success" if metadata["errors"] < len(results) else "error",
        "count": len(products),
        "metadata": metadata,
        "products": products,
    }

    if comparison_summary:
        response["comparison"] = comparison_summary

    print(json.dumps(response, indent=2, ensure_ascii=False, default=str))


def _calculate_change_indicators(
    latest: dict[str, Any] | None, previous: dict[str, Any] | None
) -> str:
    """
    Calculate change indicators comparing latest vs previous snapshot.

    Returns formatted string showing:
    - Price changes: ↑ +0.50, ↓ -0.30, ✓ Same
    - Availability: ⚠ Out of stock, ✓ Back in stock
    - Promotions: ️ New promo, ✗ Promo ended
    - First tracking: ✗ NEW
    """
    if latest is None:
        return "N/A"

    if previous is None:
        return "✗ NEW"

    indicators = []

    latest_price = latest.get("current_price")
    previous_price = previous.get("current_price")

    if latest_price is not None and previous_price is not None:
        price_diff = latest_price - previous_price
        if abs(price_diff) < 0.01:
            indicators.append("✓ Same")
        elif price_diff > 0:
            indicators.append(f"↑ +{price_diff:.2f}")
        else:
            indicators.append(f"↓ {price_diff:.2f}")

    latest_avail = latest.get("availability")
    previous_avail = previous.get("availability")

    if latest_avail != previous_avail:
        if not latest_avail:
            indicators.append("⚠ Out of stock")
        else:
            indicators.append("✓ Back in stock")

    latest_promo = latest.get("has_promotion")
    previous_promo = previous.get("has_promotion")

    if latest_promo != previous_promo:
        if latest_promo:
            indicators.append("🏷️ New promo")
        else:
            indicators.append("✗ Promo ended")

    return ", ".join(indicators) if indicators else "✓ Same"


def display_comparison_table_with_changes(
    snapshots_with_changes: dict[str, dict[str, dict[str, Any] | None]], console
):
    """Display comparison table showing latest snapshot per URL with change indicators."""

    table = Table(
        title="Product Price Comparison",
        headers=["Provider", "Product", "Amount", "Price", "Change", "Available", "Scraped At"],
    )

    total_products = 0
    providers = set()
    price_changes = {"increased": 0, "decreased": 0, "new": 0, "promo": 0}

    for _url, snapshots in snapshots_with_changes.items():
        latest = snapshots.get("latest")
        previous = snapshots.get("previous")

        if latest is None:
            continue

        total_products += 1
        provider = latest.get("provider", "unknown")
        providers.add(provider)

        # Format provider name for display (replace underscores, title case)
        provider_display = provider.replace("_", " ").title()

        name = latest.get("name", "N/A")
        product_name = _truncate_text(name, 40)
        amount_str = _get_product_amount(latest)
        price_str = _format_price(latest.get("current_price"), latest.get("currency", "EUR"))
        change_str = _calculate_change_indicators(latest, previous)

        if "✗ NEW" in change_str:
            price_changes["new"] += 1
        if "↑" in change_str:
            price_changes["increased"] += 1
        if "↓" in change_str:
            price_changes["decreased"] += 1
        if "🏷️" in change_str or "promo" in change_str.lower():
            price_changes["promo"] += 1

        availability_str = _format_boolean(latest.get("availability", False))
        scraped_at = _format_timestamp(latest.get("scraped_at", "N/A"))

        table.add_row(
            provider_display,
            product_name,
            amount_str,
            price_str,
            change_str,
            availability_str,
            scraped_at,
        )

    console.print(table)

    console.print(
        f"\n[dim]Summary: {total_products} product(s) across {len(providers)} provider(s)[/dim]"
    )

    changes = []
    if price_changes["decreased"] > 0:
        changes.append(f"{price_changes['decreased']} decreased")
    if price_changes["increased"] > 0:
        changes.append(f"{price_changes['increased']} increased")
    if price_changes["new"] > 0:
        changes.append(f"{price_changes['new']} new")
    if price_changes["promo"] > 0:
        changes.append(f"{price_changes['promo']} promo")

    if changes:
        console.print(f"[dim]Price changes: {', '.join(changes)}[/dim]")


def display_comparison_table(snapshots_by_url: dict[str, list[dict]], console):
    """Display comparison table showing last 3 snapshots per URL."""

    table = Table(
        title="Product Price Comparison",
        headers=["Provider", "Product", "Amount", "Price", "Promotion", "Available", "Scraped At"],
        expand="auto",  # type: ignore[arg-type]  # ChalkBox 2.0: Auto-expand for wide tables
    )

    total_snapshots = 0
    providers = set()
    cheapest = None
    cheapest_price = float("inf")

    for _url, snapshots in snapshots_by_url.items():
        for snapshot in snapshots:
            total_snapshots += 1
            provider = snapshot.get("provider", "unknown")
            providers.add(provider)

            name = snapshot.get("name", "N/A")
            product_name = _truncate_text(name, 40)
            amount_str = _get_product_amount(snapshot)
            current_price = snapshot.get("current_price")
            price_str = _format_price(current_price, snapshot.get("currency", "EUR"))

            if current_price and current_price < cheapest_price:
                cheapest_price = current_price
                cheapest = f"{provider} {_truncate_text(name, 30)}"

            promotion = _format_promotion(
                snapshot.get("has_promotion", False), snapshot.get("discount_percentage")
            )
            availability_str = _format_boolean(snapshot.get("availability", False))
            scraped_at = _format_timestamp(snapshot.get("scraped_at", "N/A"))

            table.add_row(
                provider,
                product_name,
                amount_str,
                price_str,
                promotion,
                availability_str,
                scraped_at,
            )

    console.print(table)

    num_products = len(snapshots_by_url)
    console.print(
        f"\n[dim]Summary: {total_snapshots} snapshots from {num_products} product(s) across {len(providers)} provider(s)[/dim]"
    )
    if cheapest and cheapest_price < float("inf"):
        console.print(f"[green]Cheapest: {cheapest} €{cheapest_price:.2f}[/green]")
