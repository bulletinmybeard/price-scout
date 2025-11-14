import logging
import time

from chalkbox.logging.bridge import get_logger

from src.cli.helpers import detect_provider_from_url
from src.database.db_manager import DatabaseManager
from src.price_tracker.group_helpers import (
    associate_tracked_page_with_group,
    auto_associate_with_groups,
)
from src.utils.datetime_utils import now_in_configured_tz

logger = get_logger(__name__)


def scrape_single_url(url, tracker, factory, check, db_url, group_name=None):
    """Scrape a single URL and return result tuple with timing."""
    start_time = time.time()

    try:
        provider_name, _provider_config = detect_provider_from_url(url, factory)
        logging.debug(f"Provider name: {provider_name}")
        logging.debug(f"Provider config: {_provider_config}")

        if not provider_name:
            elapsed = time.time() - start_time
            return "error", url, "Could not detect provider for URL", elapsed

        if check:
            product = tracker.fetch_product_only(url, provider_name)
            elapsed = time.time() - start_time

            if not product or not product.name or product.current_price is None:
                error_msg = "Extraction failed - missing required fields (name or price)"
                return "error", url, error_msg, elapsed

            result = ("scraped", url, product, elapsed)

        else:
            product, _db_result = tracker.track_product_url(url, provider_name, track_to_db=True)
            elapsed = time.time() - start_time

            if not product or not product.name or product.current_price is None:
                error_msg = "Extraction failed - missing required fields (name or price)"
                return "error", url, error_msg, elapsed

            result = ("scraped", url, product, elapsed)

            if product:
                thread_db_manager = None
                try:
                    thread_db_manager = DatabaseManager(db_url, read_only=False)

                    tracked_url = product.url

                    existing_page = thread_db_manager.get_tracked_page(tracked_url)
                    if existing_page:
                        thread_db_manager.update_last_checked(tracked_url, product.current_price)
                    else:
                        page_data = {
                            "url": tracked_url,
                            "provider": provider_name,
                            "enabled": True,
                            "last_checked": now_in_configured_tz(),
                            "last_price": product.current_price,
                        }
                        thread_db_manager.add_tracked_page(page_data)

                    if group_name:
                        associate_tracked_page_with_group(
                            tracked_url, group_name, thread_db_manager
                        )
                    else:
                        associated_groups = auto_associate_with_groups(
                            tracked_url, thread_db_manager
                        )
                        if associated_groups:
                            logger.debug(
                                f"Auto-associated URL with groups: {', '.join(associated_groups)}"
                            )

                except Exception as e:
                    if "foreign key constraint" in str(e).lower():
                        logger.debug(f"Foreign key constraint during page update for {url}: {e}")
                    else:
                        logger.error(f"Failed to add tracked_page for {url}: {e}")

                finally:
                    if thread_db_manager:
                        logger.debug(f"Database operations completed for {url}")

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        return "error", url, str(e), elapsed
