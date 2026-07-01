import time

from chalkbox.logging.bridge import get_logger

from src.cli.helpers import detect_provider_from_url

logger = get_logger(__name__)


def scrape_single_url(url, tracker, factory, check, db_url, group_name=None):
    start_time = time.time()

    try:
        provider_name, _provider_config = detect_provider_from_url(url, factory)
        logger.debug(f"Provider name: {provider_name}")
        logger.debug(f"Provider config: {_provider_config}")

        if not provider_name:
            elapsed = time.time() - start_time
            return "error", url, "Could not detect provider for URL", elapsed

        if check:
            product = tracker.fetch_product_only(url, provider_name)
        else:
            product, _db_result = tracker.track_product_url(
                url,
                provider_name,
                track_to_db=True,
                group_name=group_name,
                auto_associate_groups=group_name is None,
            )

        elapsed = time.time() - start_time

        if not product:
            error_msg = "Extraction failed - no product data returned"
            return "error", url, error_msg, elapsed

        price_missing = product.current_price is None and not product.is_marketplace_only
        if not product.name or price_missing:
            error_msg = "Extraction failed - missing required fields (name or price)"
            return "error", url, error_msg, elapsed

        return ("scraped", url, product, elapsed)

    except Exception as e:
        elapsed = time.time() - start_time
        return "error", url, str(e), elapsed
