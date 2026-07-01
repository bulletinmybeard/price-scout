import asyncio
from typing import Any

from chalkbox.logging.bridge import get_logger

from src.database.db_manager import DatabaseManager
from src.price_tracker.persistence import persist_scrape_result
from src.providers import get_factory

logger = get_logger(__name__)

BACKGROUND_CLEANUP_DELAY = 0.2


class PriceTracker:
    """Orchestrates price tracking across multiple store providers."""

    def __init__(self, db_manager: DatabaseManager, headless: bool | None = None):
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
        try:
            return self.factory.get_provider(provider_name, headless=self.headless)
        except ValueError as e:
            logger.error(f"Provider '{provider_name}' not found: {e}")
            return None

    def list_providers(self) -> list[str]:
        return self.factory.list_providers()

    def fetch_product_only(self, url: str, provider_name: str):
        return asyncio.run(self._fetch_product_only_async(url, provider_name))

    async def _fetch_product_only_async(self, url: str, provider_name: str):
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
        self,
        url: str,
        provider_name: str,
        track_to_db: bool = True,
        *,
        group_name: str | None = None,
        auto_associate_groups: bool = False,
    ) -> tuple[Any, dict | None]:
        return asyncio.run(
            self._track_product_url_async(
                url,
                provider_name,
                track_to_db,
                group_name=group_name,
                auto_associate_groups=auto_associate_groups,
            )
        )

    async def _track_product_url_async(
        self,
        url: str,
        provider_name: str,
        track_to_db: bool = True,
        *,
        group_name: str | None = None,
        auto_associate_groups: bool = False,
    ) -> tuple[Any, dict | None]:
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

                db_result = persist_scrape_result(
                    self.db_manager,
                    product_data,
                    provider_name,
                    group_name=group_name,
                    auto_associate_groups=auto_associate_groups,
                )

                logger.debug(
                    f"Successfully tracked: {product_data.name} @ {provider_name} - "
                    f"{product_data.currency} {product_data.current_price}"
                )
                await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
                return product_data, db_result

        except Exception as e:
            logger.error(f"Error tracking product from {url}: {e}", exc_info=True)
            await asyncio.sleep(BACKGROUND_CLEANUP_DELAY)
            return None, None
