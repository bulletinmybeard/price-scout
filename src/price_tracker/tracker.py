import asyncio
from typing import Any

from chalkbox.logging.bridge import get_logger

from src.database.db_manager import DatabaseManager
from src.providers import get_factory
from src.utils.datetime_utils import now_in_configured_tz

logger = get_logger(__name__)

BACKGROUND_CLEANUP_DELAY = 0.2


class PriceTracker:
    """Orchestrates price tracking across multiple store providers."""

    def __init__(self, db_manager: DatabaseManager, headless: bool | None = None):
        """Initialize the PriceTracker."""
        self.db_manager = db_manager
        self.factory = get_factory()

        if headless is None:
            scraping_config = self.factory.full_config.get("scraping", {})
            self.headless = scraping_config.get("headless", True)
        else:
            self.headless = headless

        logger.debug(
            f"PriceTracker initialized with {len(self.factory.list_providers())} providers "
            f"(headless={self.headless})"
        )

    def get_provider(self, provider_name: str):
        """Get a provider instance by name."""
        try:
            return self.factory.get_provider(provider_name, headless=self.headless)
        except ValueError as e:
            logger.error(f"Provider '{provider_name}' not found: {e}")
            return None

    def list_providers(self) -> list[str]:
        """Get a list of all available provider names."""
        return self.factory.list_providers()

    def fetch_product_only(self, url: str, provider_name: str):
        """Fetch product details without tracking to database."""
        return asyncio.run(self._fetch_product_only_async(url, provider_name))

    async def _fetch_product_only_async(self, url: str, provider_name: str):
        """Async implementation of fetch_product_only."""
        try:
            async with self.factory.get_provider(provider_name, headless=self.headless) as provider:
                product = await provider.get_product_details(url)
                await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
                return product
        except Exception as e:
            logger.error(f"Error fetching product from {url}: {e}", exc_info=True)
            await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
            return None

    def track_product_url(
        self, url: str, provider_name: str, track_to_db: bool = True
    ) -> tuple[Any, dict | None]:
        """Track a product from a specific URL."""
        return asyncio.run(self._track_product_url_async(url, provider_name, track_to_db))

    async def _track_product_url_async(
        self, url: str, provider_name: str, track_to_db: bool = True
    ) -> tuple[Any, dict | None]:
        """Async implementation of track_product_url."""
        logger.debug(f"Tracking product from: {url}")

        try:
            async with self.factory.get_provider(provider_name, headless=self.headless) as provider:
                product_data = await provider.get_product_details(url)

                if not product_data:
                    logger.error(f"Failed to scrape product from: {url}")
                    await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
                    return None, None

                if not track_to_db:
                    await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
                    return product_data, None

                snapshot_data = {
                    "url": url,
                    "provider": provider_name,
                    "name": product_data.name,
                    "brand": product_data.brand,
                    "current_price": float(product_data.current_price)
                    if product_data.current_price
                    else None,
                    "original_price": float(product_data.original_price)
                    if product_data.original_price
                    else None,
                    "currency": product_data.currency,
                    "availability": product_data.availability,
                    "availability_text": product_data.availability_text,
                    "has_promotion": product_data.has_promotion,
                    "discount_percentage": product_data.discount_percentage,
                    "sku": product_data.sku,
                    "gtin": product_data.gtin,
                    "image_url": product_data.image,
                    "description": product_data.description,
                    "category": product_data.category,  # JSON field, pass list directly
                    "weight": product_data.weight,
                    "extraction_method": product_data.extraction_method,
                    "scraped_at": now_in_configured_tz(),
                }

                snapshot_id = self.db_manager.add_snapshot(snapshot_data)

                db_result = {
                    "snapshot_id": snapshot_id,
                    "product_name": product_data.name,
                    "provider": provider_name,
                    "price": product_data.current_price,
                    "currency": product_data.currency,
                    "is_available": product_data.availability,
                    "scraped_at": now_in_configured_tz(),
                }

                logger.debug(
                    f"Successfully tracked: {product_data.name} @ {provider_name} - {product_data.currency} {product_data.current_price}"
                )
                await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
                return product_data, db_result

        except Exception as e:
            logger.error(f"Error tracking product from {url}: {e}", exc_info=True)
            await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
            return None, None
