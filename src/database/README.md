# Database Schema Documentation

## Overview

The database schema has been updated to match the **BaseProduct** schema with **40+ fields**, providing comprehensive tracking of all product attributes including pricing, promotions, availability, physical properties, and more.

## Architecture

The database uses a **snapshot-based architecture**:

- **tracked_pages**: URLs being monitored
- **page_snapshots**: Historical price/product data snapshots
- **product_groups**: Groups for price comparison
- **page_groups**: Many-to-many relationship table

**Note**: Price alerts feature is planned for v1.2

This design allows tracking how **ALL** product attributes change over time, not just price.

## Schema Details

### Product Table

**Purpose**: Master record with core product identifiers

**Fields**:

- `product_id` (PK): Auto-increment primary key
- **Core Identification**:
  - `name`: Product name/title
  - `sku`: Store-specific product code
  - `gtin`: Global Trade Item Number (EAN/UPC barcode)
  - `brand`: Brand name
  - `manufacturer`: Manufacturer (if different from brand)
- **Categorization** (JSON):
  - `category`: List of categories (e.g., `["Groceries", "Snacks", "Nuts"]`)
  - `tags`: Product tags/labels
- **Basic Content**:
  - `description`: Product description
  - `image_url`: Primary product image
- **Timestamps**:
  - `created_at`: When product was first added
  - `updated_at`: Last update time

**Indexes**:

- `idx_product_name`
- `idx_product_sku`
- `idx_product_gtin`
- `idx_product_brand`

### Price Table

**Purpose**: Complete snapshot of product data at a specific point in time

**Fields**:

- `price_id` (PK): Auto-increment primary key
- `product_id` (FK): Reference to Product
- `store_id` (FK): Reference to Store
- `url`: Product page URL at time of scraping

**Pricing**:

- `current_price`: Current selling price (required)
- `original_price`: Original price before discount
- `currency`: ISO currency code (EUR, USD, etc.)
- `price_per_unit`: e.g., "€1.50/kg"

**Promotion Tracking**:

- `has_promotion`: Boolean flag
- `discount_percentage`: Percentage discount
- `promotion_text`: e.g., "2 for 1", "Save 50%"
- `promotion_ends_at`: Promotion end date

**Availability & Stock**:

- `availability`: Is product available
- `stock_quantity`: Number in stock
- `availability_text`: e.g., "In stock", "Low stock"
- `max_order_quantity`: Maximum items per order

**Content**:

- `short_description`: Brief description/subtitle
- `features`: JSON list of product features

**Media**:

- `images`: JSON list of all product image URLs

**Ratings & Reviews**:

- `rating`: Average rating (e.g., 4.5)
- `rating_count`: Number of ratings
- `review_count`: Number of reviews

**Physical Properties**:

- `weight`: e.g., "500g"
- `dimensions`: e.g., "10x20x5 cm"
- `volume`: e.g., "1L"
- `color`: Product color
- `size`: Product size

**Food-Specific** (JSON):

- `ingredients`: Ingredient list
- `nutrition_info`: Nutrition facts dict
- `allergens`: List of allergens
- `dietary_info`: e.g., ["vegan", "gluten-free"]

**Shipping**:

- `shipping_cost`: Shipping cost
- `free_shipping`: Boolean flag
- `delivery_time`: e.g., "2-3 days"

**Metadata**:

- `extraction_method`: "json-ld", "opengraph", or "css"
- `raw_data`: Original scraped data (JSON)
- `scraped_at`: When data was scraped

**Indexes**:

- `idx_price_product_store`
- `idx_price_scraped_at`
- `idx_price_availability`
- `idx_price_promotion`

### Store Table

**Purpose**: Retailer/merchant information

**Fields**:

- `store_id` (PK)
- `name`: Store name
- `country`: ISO country code
- `base_url`: Store website
- `provider_class`: Python provider class name
- `is_active`: Whether store is actively tracked
- `created_at`, `updated_at`: Timestamps

## Migration

### For New Databases

Simply run:

```bash
poetry run python examples/database/save_product_example.py
```

This will create all tables with the new schema.

### For Existing Databases

**Option 1: Fresh Start** (Recommended for development):

```bash
rm price_tracker.db  # Delete old database
poetry run python examples/database/save_product_example.py
```

**Option 2: Migration Script** (For production with existing data):

```bash
poetry run python src/database/migrations/001_add_baseproduct_fields.py
```

**Warning**: Back up your database before running migrations!

The migration script will:

1. Add new columns to existing tables
1. Migrate data from old columns to new ones
1. Preserve existing data

## Usage Example

### Saving Scraped Data

```python
from src.database.db_manager import DatabaseManager
from src.database.converters import save_base_product
from src.providers.store_a import StoreAProvider

# Initialize database
db = DatabaseManager(db_url="sqlite:///./price_tracker.db")
db.create_database()

# Scrape product
async with StoreAProvider() as provider:
    product = await provider.get_product_details(url)

    # Save to database
    with db.get_db() as session:
        db_product, db_price = save_base_product(
            session,
            product,
            store_id=1  # Store-A store ID
        )
        session.commit()
```

### Querying Data

```python
from src.database.models import Product, Price

# Get all products
with db.get_db() as session:
    products = session.query(Product).all()

    for product in products:
        # Get latest price
        latest = session.query(Price).filter(
            Price.product_id == product.product_id
        ).order_by(Price.scraped_at.desc()).first()

        print(f"{product.name}: {latest.current_price} {latest.currency}")
        if latest.has_promotion:
            print(f"  ON SALE: {latest.discount_percentage:.1f}% OFF")
```

### Tracking Price History

```python
# Get all price records for a product
with db.get_db() as session:
    prices = session.query(Price).filter(
        Price.product_id == 1
    ).order_by(Price.scraped_at.desc()).all()

    for price in prices:
        print(f"{price.scraped_at}: {price.current_price} {price.currency}")
```

## JSON Field Storage

Several fields use JSON for storing complex types:

- **Lists**: `category`, `tags`, `features`, `images`, `allergens`, `dietary_info`
- **Dicts**: `nutrition_info`, `raw_data`

These are stored as JSON in SQLite and can be queried/filtered using SQLAlchemy's JSON operators.

## Field Mapping: BaseProduct → Database

| BaseProduct Field   | Database Location         | Type        |
| ------------------- | ------------------------- | ----------- |
| name                | Product.name              | String      |
| url                 | Price.url                 | String      |
| current_price       | Price.current_price       | Float       |
| original_price      | Price.original_price      | Float       |
| currency            | Price.currency            | String      |
| price_per_unit      | Price.price_per_unit      | String      |
| has_promotion       | Price.has_promotion       | Boolean     |
| discount_percentage | Price.discount_percentage | Float       |
| promotion_text      | Price.promotion_text      | String      |
| promotion_ends_at   | Price.promotion_ends_at   | DateTime    |
| sku                 | Product.sku               | String      |
| gtin                | Product.gtin              | String      |
| brand               | Product.brand             | String      |
| manufacturer        | Product.manufacturer      | String      |
| category            | Product.category          | JSON (list) |
| tags                | Product.tags              | JSON (list) |
| availability        | Price.availability        | Boolean     |
| stock_quantity      | Price.stock_quantity      | Integer     |
| availability_text   | Price.availability_text   | String      |
| description         | Product.description       | Text        |
| short_description   | Price.short_description   | Text        |
| features            | Price.features            | JSON (list) |
| image               | Product.image_url         | String      |
| images              | Price.images              | JSON (list) |
| rating              | Price.rating              | Float       |
| weight              | Price.weight              | String      |
| ingredients         | Price.ingredients         | Text        |
| nutrition_info      | Price.nutrition_info      | JSON (dict) |
| allergens           | Price.allergens           | JSON (list) |
| dietary_info        | Price.dietary_info        | JSON (list) |
| shipping_cost       | Price.shipping_cost       | Float       |
| free_shipping       | Price.free_shipping       | Boolean     |
| delivery_time       | Price.delivery_time       | String      |
| provider            | Store (via store_id)      | -           |
| extraction_method   | Price.extraction_method   | String      |
| extracted_at        | Price.scraped_at          | DateTime    |
| raw_data            | Price.raw_data            | JSON (dict) |

## Benefits of This Architecture

1. **Complete History**: Track changes to ALL fields over time, not just price
1. **Flexible Schema**: JSON fields support varying data structures across providers
1. **Fast Queries**: Indexes on common query patterns (product, store, date, promotion)
1. **Data Integrity**: Foreign keys maintain relationships
1. **Scalable**: Snapshot model works for any number of products/stores
1. **Provider-Agnostic**: Universal schema works for any e-commerce site

## Notes

- Product table stores **master record** with identifiers
- Price table stores **complete snapshots** at each scraping
- This allows tracking how products evolve (price, description, images, etc.)
- Category as JSON list enables hierarchical categorization
- Raw data field preserves original JSON-LD/OpenGraph for debugging
- Timestamps use UTC (datetime.utcnow())
