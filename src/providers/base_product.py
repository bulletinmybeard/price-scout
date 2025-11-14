from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BaseProduct:
    """Universal product schema for retailer scraping."""

    name: str  # Product name/title
    url: str  # Product page URL

    current_price: float | None = None  # Current selling price
    original_price: float | None = None  # Original price (before discount)
    currency: str = "EUR"  # ISO 4217 currency code (EUR, USD, GBP, etc.)
    price_per_unit: str | None = None  # e.g., "€1.50/kg", "£2.00/liter"

    has_promotion: bool = False  # Is product currently on promotion/sale
    discount_percentage: float | None = None  # Discount % if on promotion
    promotion_text: str | None = None  # e.g., "2 for 1", "Save 50%"
    promotion_ends_at: datetime | None = None  # Promotion end date

    sku: str | None = None  # Store's internal product code
    gtin: str | None = None  # Global Trade Item Number (barcode/EAN)
    brand: str | None = None  # Brand name
    manufacturer: str | None = None  # Manufacturer (if different from brand)

    category: list[str] = field(default_factory=list)  # Category hierarchy
    tags: list[str] = field(default_factory=list)  # Product tags/labels

    availability: bool = True  # Is product available for purchase
    stock_quantity: int | None = None  # Number of items in stock
    availability_text: str | None = None  # e.g., "In stock", "Low stock"
    max_order_quantity: int | None = None  # Maximum items per order

    description: str | None = None  # Product description
    short_description: str | None = None  # Brief description/subtitle
    features: list[str] = field(default_factory=list)  # Product features/bullets

    image: str | None = None  # Primary product image URL
    images: list[str] = field(default_factory=list)  # All product images

    rating: float | None = None  # Average rating (e.g., 4.5)
    rating_count: int | None = None  # Number of ratings
    review_count: int | None = None  # Number of reviews

    weight: str | None = None  # e.g., "500g", "1kg"
    dimensions: str | None = None  # e.g., "10x20x5 cm"
    volume: str | None = None  # e.g., "1L", "500ml"
    color: str | None = None  # Product color
    size: str | None = None  # Product size (clothing, etc.)

    amount_value: float | None = None  # Numeric value (e.g., 500, 1.5)
    amount_unit: str | None = None  # Normalized unit (e.g., "g", "ml", "kg", "l")
    pack_quantity: int = 1  # Multi-pack count (e.g., 6 for "6 x 330ml")

    variant_color: str | None = None  # Extracted color (e.g., "red", "blue")
    variant_flavor: str | None = None  # Extracted flavor (e.g., "chocolate", "vanilla")
    variant_type: str | None = None  # Extracted type (e.g., "organic", "bio", "zero")

    ingredients: str | None = None  # Ingredient list
    nutrition_info: dict[str, Any] = field(default_factory=dict)  # Nutrition facts
    allergens: list[str] = field(default_factory=list)  # Allergen warnings
    dietary_info: list[str] = field(default_factory=list)  # e.g., "vegan", "gluten-free"

    shipping_cost: float | None = None  # Shipping cost
    free_shipping: bool = False  # Free shipping available
    delivery_time: str | None = None  # e.g., "2-3 days"

    provider: str | None = None  # Provider name (e.g., "store_a", "store_b")
    extraction_method: str | None = None  # "json-ld"
    extracted_at: datetime | None = None  # When data was extracted
    raw_data: dict[str, Any] = field(default_factory=dict)  # Original raw data

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "current_price": self.current_price,
            "original_price": self.original_price,
            "currency": self.currency,
            "price_per_unit": self.price_per_unit,
            "has_promotion": self.has_promotion,
            "discount_percentage": self.discount_percentage,
            "promotion_text": self.promotion_text,
            "promotion_ends_at": self.promotion_ends_at.isoformat()
            if self.promotion_ends_at
            else None,
            "sku": self.sku,
            "gtin": self.gtin,
            "brand": self.brand,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "tags": self.tags,
            "availability": self.availability,
            "stock_quantity": self.stock_quantity,
            "availability_text": self.availability_text,
            "max_order_quantity": self.max_order_quantity,
            "description": self.description,
            "short_description": self.short_description,
            "features": self.features,
            "image": self.image,
            "images": self.images,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "review_count": self.review_count,
            "weight": self.weight,
            "dimensions": self.dimensions,
            "volume": self.volume,
            "color": self.color,
            "size": self.size,
            "ingredients": self.ingredients,
            "nutrition_info": self.nutrition_info,
            "allergens": self.allergens,
            "dietary_info": self.dietary_info,
            "shipping_cost": self.shipping_cost,
            "free_shipping": self.free_shipping,
            "delivery_time": self.delivery_time,
            "provider": self.provider,
            "extraction_method": self.extraction_method,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseProduct":
        if data.get("extracted_at") and isinstance(data["extracted_at"], str):
            data["extracted_at"] = datetime.fromisoformat(data["extracted_at"])
        if data.get("promotion_ends_at") and isinstance(data["promotion_ends_at"], str):
            data["promotion_ends_at"] = datetime.fromisoformat(data["promotion_ends_at"])

        return cls(**data)

    def __repr__(self) -> str:
        price_str = f"{self.currency} {self.current_price}" if self.current_price else "N/A"
        return f"<Product: {self.name[:50]}... | Price: {price_str} | Provider: {self.provider}>"
