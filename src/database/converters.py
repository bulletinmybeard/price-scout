from typing import Any

from chalkbox.logging.bridge import get_logger

from src.providers.base_product import BaseProduct
from src.utils.datetime_utils import now_in_configured_tz

logger = get_logger(__name__)


def base_product_to_snapshot(base_product: BaseProduct, provider: str, url: str) -> dict[str, Any]:
    """Convert BaseProduct to page snapshot dictionary for DuckDB."""

    snapshot = {
        "url": url,
        "provider": provider,
        "name": base_product.name,
        "description": base_product.description,
        "brand": base_product.brand,
        "manufacturer": base_product.manufacturer,
        "sku": base_product.sku,
        "gtin": base_product.gtin,
        "current_price": base_product.current_price,
        "original_price": base_product.original_price,
        "currency": base_product.currency or "EUR",
        "price_per_unit": base_product.price_per_unit,
        "has_promotion": base_product.has_promotion or False,
        "discount_percentage": base_product.discount_percentage,
        "promotion_text": base_product.promotion_text,
        "promotion_ends_at": base_product.promotion_ends_at,
        "availability": base_product.availability,
        "stock_quantity": base_product.stock_quantity,
        "availability_text": base_product.availability_text,
        "max_order_quantity": base_product.max_order_quantity,
        "short_description": base_product.short_description,
        "features": base_product.features,
        "category": base_product.category,
        "tags": base_product.tags,
        "image_url": base_product.image,
        "images": base_product.images,
        "rating": base_product.rating,
        "rating_count": base_product.rating_count,
        "review_count": base_product.review_count,
        "weight": base_product.weight,
        "dimensions": base_product.dimensions,
        "volume": base_product.volume,
        "color": base_product.color,
        "size": base_product.size,
        "ingredients": base_product.ingredients,
        "nutrition_info": base_product.nutrition_info,
        "allergens": base_product.allergens,
        "dietary_info": base_product.dietary_info,
        "shipping_cost": base_product.shipping_cost,
        "free_shipping": base_product.free_shipping or False,
        "delivery_time": base_product.delivery_time,
        "extraction_method": base_product.extraction_method,
        "structured_data": base_product.raw_data,
        "scraped_at": base_product.extracted_at or now_in_configured_tz(),
    }

    logger.debug(
        f"Converted {provider} product to snapshot: {base_product.name} "
        f"(€{base_product.current_price}, promo={base_product.has_promotion})"
    )

    return snapshot


base_product_to_models = base_product_to_snapshot
