from typing import Any

from chalkbox.logging.bridge import get_logger

from src.database.db_manager import DatabaseManager

logger = get_logger(__name__)


class PriceComparator:
    """Compares product prices across different stores and provides analysis."""

    def __init__(self, db_manager: DatabaseManager | None = None):
        """Initialize the PriceComparator."""
        self.db_manager = db_manager or DatabaseManager()
        logger.debug("PriceComparator initialized with DuckDB backend")

    def compare_group(self, group_name: str) -> dict[str, Any]:
        """Compare prices for all providers in a product group."""
        logger.debug(f"Comparing prices for group '{group_name}'")
        return self.db_manager.get_group_comparison(group_name)

    def find_cheapest_in_group(self, group_name: str) -> dict[str, Any] | None:
        """Find the provider with the lowest price in a group."""
        logger.debug(f"Finding cheapest provider in group '{group_name}'")
        return self.db_manager.get_cheapest_in_group(group_name)

    def get_group_price_history(self, group_name: str, days: int = 30) -> list[dict[str, Any]]:
        """Get price history for all providers in a group."""
        logger.debug(f"Getting price history for group '{group_name}' ({days} days)")
        return self.db_manager.get_group_price_history(group_name, days)

    def get_group_statistics(self, group_name: str) -> dict[str, Any]:
        """Get statistical summary for a product group."""
        logger.debug(f"Getting statistics for group '{group_name}'")
        stats = self.db_manager.get_group_statistics(group_name)
        return stats or {}

    def get_all_groups_summary(self) -> list[dict[str, Any]]:
        """Get a summary of all product groups with their best prices."""
        logger.debug("Getting summary for all product groups")
        groups = self.db_manager.get_all_groups()

        summaries = []
        for group in groups:
            group_name = group["name"]

            comparison = self.db_manager.get_group_comparison(group_name)

            summary = {
                "group_id": group["group_id"],
                "group_name": group_name,
                "description": group.get("description"),
                "page_count": group.get("page_count", 0),
                "statistics": comparison.get("statistics"),
                "cheapest_provider": comparison.get("cheapest_provider"),
            }

            summaries.append(summary)

        return summaries

    def find_best_deals(
        self,
        _category: str | None = None,
        limit: int = 10,
        discount_threshold: float = 0.15,
    ) -> list[dict[str, Any]]:
        """Find the best deals across all tracked products."""
        logger.debug(f"Finding best deals (discount >= {discount_threshold * 100}%)")

        deals = []

        promotions = self.db_manager.get_active_promotions()

        for promo in promotions:
            discount = promo.get("discount_percentage")
            if discount and discount >= (discount_threshold * 100):
                deals.append(
                    {
                        "provider": promo.get("provider"),
                        "product_name": promo.get("name"),
                        "url": promo.get("url"),
                        "current_price": promo.get("current_price"),
                        "original_price": promo.get("original_price"),
                        "discount_percentage": discount,
                        "promotion_text": promo.get("promotion_text"),
                        "scraped_at": promo.get("scraped_at"),
                    }
                )

        deals.sort(key=lambda x: x.get("discount_percentage", 0), reverse=True)

        return deals[:limit]

    def get_price_history(self, url: str, days: int = 30) -> list[dict[str, Any]]:
        """Get price history for a specific product URL."""
        logger.debug(f"Getting price history for {url} ({days} days)")
        return self.db_manager.get_snapshot_history(url, days)
