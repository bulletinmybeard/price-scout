from pathlib import Path
from typing import Any

from chalkbox.logging.bridge import get_logger
import yaml

from src.models.tracked_product import TrackedProduct

logger = get_logger(__name__)


def get_config_path(config_path: str | None = None) -> Path:
    if config_path:
        return Path(config_path)

    return Path(__file__).parent.parent.parent / "config.yaml"


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load full configuration from config.yaml."""
    path = get_config_path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f) or {}
        logger.debug(f"Loaded config from {path}")
        return config
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config: {e}")
        raise


def load_tracked_products(config_path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load all tracked product pages from config."""
    config = load_config(config_path)
    tracked = {}

    providers = config.get("providers", {})
    logger.info(f"Loading tracked products from {len(providers)} providers")

    for provider_name, provider_config in providers.items():
        product_pages = provider_config.get("product_pages", [])

        if product_pages:
            logger.info(f"Found {len(product_pages)} tracked products for {provider_name}")

            for page in product_pages:
                page["provider"] = provider_name

            tracked[provider_name] = product_pages
        else:
            logger.debug(f"No tracked products for {provider_name}")
            tracked[provider_name] = []

    total = sum(len(pages) for pages in tracked.values())
    logger.info(f"Loaded {total} total tracked products")

    return tracked


def get_enabled_products(
    provider: str | None = None, config_path: str | None = None
) -> list[dict[str, Any]]:
    """Get all enabled product pages."""
    all_products = load_tracked_products(config_path)

    if provider:
        products = all_products.get(provider, [])
    else:
        products = []
        for pages in all_products.values():
            products.extend(pages)

    enabled = [p for p in products if p.get("enabled", True)]

    logger.info(f"Found {len(enabled)} enabled products" + (f" for {provider}" if provider else ""))

    return enabled


def get_product_by_url(url: str, config_path: str | None = None) -> dict[str, Any] | None:
    """Find a tracked product by URL."""
    all_products = load_tracked_products(config_path)

    for _provider, products in all_products.items():
        for product in products:
            if product.get("url") == url:
                return product

    return None


def get_products_by_tag(tag: str, config_path: str | None = None) -> list[dict[str, Any]]:
    """Get all products with a specific tag."""
    all_products = load_tracked_products(config_path)
    matches = []

    for _provider, products in all_products.items():
        for product in products:
            tags = product.get("tags", [])
            if tag in tags:
                matches.append(product)

    logger.info(f"Found {len(matches)} products with tag '{tag}'")
    return matches


def get_products_by_priority(priority: str, config_path: str | None = None) -> list[dict[str, Any]]:
    """Get all products with a specific priority."""
    all_products = load_tracked_products(config_path)
    matches = []

    for _provider, products in all_products.items():
        for product in products:
            if product.get("priority", "medium") == priority:
                matches.append(product)

    logger.info(f"Found {len(matches)} products with priority '{priority}'")
    return matches


def load_as_tracked_product_models(
    provider: str | None = None, config_path: str | None = None
) -> list[TrackedProduct]:
    """Load product pages as TrackedProduct model instances."""
    products = get_enabled_products(provider, config_path)
    return [TrackedProduct.from_dict(p) for p in products]


def get_provider_defaults(provider: str, config_path: str | None = None) -> dict[str, Any]:
    """Get default settings for a provider."""
    config = load_config(config_path)
    provider_config = config.get("providers", {}).get(provider, {})

    return {
        "name": provider_config.get("name"),
        "country": provider_config.get("country"),
        "base_url": provider_config.get("base_url"),
    }
