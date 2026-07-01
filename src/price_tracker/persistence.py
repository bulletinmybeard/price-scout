"""Unified persistence for scrape results (snapshots + tracked pages + groups)."""

from typing import Any

from chalkbox.logging.bridge import get_logger

from src.database.db_manager import DatabaseManager
from src.price_tracker.group_helpers import (
    associate_tracked_page_with_group,
    auto_associate_with_groups,
)
from src.providers.base_product import BaseProduct
from src.utils.datetime_utils import now_in_configured_tz

logger = get_logger(__name__)


def build_snapshot_data(product: BaseProduct, provider_name: str) -> dict[str, Any]:
    """Build page_snapshots row from a scraped product."""
    return {
        "url": product.url,
        "provider": provider_name,
        "name": product.name,
        "brand": product.brand,
        "current_price": float(product.current_price) if product.current_price else None,
        "original_price": float(product.original_price) if product.original_price else None,
        "currency": product.currency,
        "availability": product.availability,
        "is_marketplace_only": product.is_marketplace_only,
        "availability_text": product.availability_text,
        "has_promotion": product.has_promotion,
        "discount_percentage": product.discount_percentage,
        "promotion_starts_at": product.promotion_starts_at,
        "promotion_ends_at": product.promotion_ends_at,
        "sku": product.sku,
        "gtin": product.gtin,
        "image_url": product.image,
        "description": product.description,
        "category": product.category,
        "weight": product.weight,
        "extraction_method": product.extraction_method,
        "scraped_at": now_in_configured_tz(),
    }


def persist_scrape_result(
    db_manager: DatabaseManager,
    product: BaseProduct,
    provider_name: str,
    *,
    group_name: str | None = None,
    auto_associate_groups: bool = True,
) -> dict[str, Any]:
    """Persist snapshot and keep tracked_pages in sync.

    Locks offer_selection_strategy on the first snapshot using the strategy
    that was actually applied during extraction.
    """
    url = product.url
    snapshots_before = db_manager.get_snapshot_count(url)
    strategy = product.offer_selection_strategy or "first"

    snapshot_id = db_manager.add_snapshot(build_snapshot_data(product, provider_name))

    existing_page = db_manager.get_tracked_page(url)
    if existing_page:
        db_manager.update_last_checked(url, product.current_price)
        if snapshots_before == 0:
            db_manager.update_offer_selection_strategy(url, strategy)
    else:
        db_manager.add_tracked_page(
            {
                "url": url,
                "provider": provider_name,
                "offer_selection_strategy": strategy,
                "enabled": True,
                "last_checked": now_in_configured_tz(),
                "last_price": product.current_price,
            }
        )

    if group_name:
        associate_tracked_page_with_group(url, group_name, db_manager)
    elif auto_associate_groups:
        associated = auto_associate_with_groups(url, db_manager)
        if associated:
            logger.debug(f"Auto-associated URL with groups: {', '.join(associated)}")

    return {
        "snapshot_id": snapshot_id,
        "product_name": product.name,
        "provider": provider_name,
        "price": product.current_price,
        "currency": product.currency,
        "is_available": product.availability,
        "scraped_at": now_in_configured_tz(),
    }
