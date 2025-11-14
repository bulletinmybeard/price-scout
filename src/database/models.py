# Sequences for auto-increment IDs
CREATE_SEQUENCES = [
    "CREATE SEQUENCE IF NOT EXISTS seq_page_snapshots_id START 1;",
    "CREATE SEQUENCE IF NOT EXISTS seq_tracked_pages_id START 1;",
    "CREATE SEQUENCE IF NOT EXISTS seq_product_groups_id START 1;",
]

CREATE_PAGE_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS page_snapshots (
    -- Primary Key (auto-increment using sequence)
    snapshot_id INTEGER PRIMARY KEY DEFAULT nextval('seq_page_snapshots_id'),
    url VARCHAR(500) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    name VARCHAR(255),
    description TEXT,
    brand VARCHAR(100),
    manufacturer VARCHAR(100),
    sku VARCHAR(100),
    gtin VARCHAR(100),
    current_price DOUBLE,
    original_price DOUBLE,
    currency VARCHAR(3) DEFAULT 'EUR',
    price_per_unit VARCHAR(50),
    has_promotion BOOLEAN DEFAULT FALSE,
    discount_percentage DOUBLE,
    promotion_text VARCHAR(255),
    promotion_ends_at TIMESTAMP,
    availability BOOLEAN DEFAULT TRUE,
    stock_quantity INTEGER,
    availability_text VARCHAR(100),
    max_order_quantity INTEGER,
    short_description TEXT,
    features JSON,
    category JSON,
    tags JSON,
    image_url VARCHAR(500),
    images JSON,
    rating DOUBLE,
    rating_count INTEGER,
    review_count INTEGER,
    weight VARCHAR(50),
    dimensions VARCHAR(100),
    volume VARCHAR(50),
    color VARCHAR(50),
    size VARCHAR(50),
    amount_value DOUBLE,
    amount_unit VARCHAR(10),
    pack_quantity INTEGER DEFAULT 1,
    variant_color VARCHAR(50),
    variant_flavor VARCHAR(50),
    variant_type VARCHAR(50),
    ingredients TEXT,
    nutrition_info JSON,
    allergens JSON,
    dietary_info JSON,
    shipping_cost DOUBLE,
    free_shipping BOOLEAN DEFAULT FALSE,
    delivery_time VARCHAR(100),
    extraction_method VARCHAR(20),
    structured_data JSON,
    scraped_at TIMESTAMP NOT NULL
);
"""

# Indexes for page_snapshots (created separately in DuckDB)
CREATE_PAGE_SNAPSHOTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_url_scraped ON page_snapshots(url, scraped_at);",
    "CREATE INDEX IF NOT EXISTS idx_provider_scraped ON page_snapshots(provider, scraped_at);",
    "CREATE INDEX IF NOT EXISTS idx_scraped_at ON page_snapshots(scraped_at);",
    "CREATE INDEX IF NOT EXISTS idx_has_promotion ON page_snapshots(has_promotion);",
]

CREATE_TRACKED_PAGES_TABLE = """
CREATE TABLE IF NOT EXISTS tracked_pages (
    id INTEGER PRIMARY KEY DEFAULT nextval('seq_tracked_pages_id'),
    url VARCHAR(500) UNIQUE NOT NULL,
    provider VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    last_checked TIMESTAMP,
    last_price DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Indexes for tracked_pages
CREATE_TRACKED_PAGES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_enabled_last_checked ON tracked_pages(enabled, last_checked);",
    "CREATE INDEX IF NOT EXISTS idx_provider ON tracked_pages(provider);",
    "CREATE INDEX IF NOT EXISTS idx_tracked_pages_url ON tracked_pages(url);",
]

CREATE_PRODUCT_GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS product_groups (
    group_id INTEGER PRIMARY KEY DEFAULT nextval('seq_product_groups_id'),
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE,
    description TEXT,
    category VARCHAR(50),
    weekly_usage DOUBLE,
    meal_type VARCHAR(50),
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PAGE_GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS page_groups (
    page_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (page_id, group_id),
    FOREIGN KEY (page_id) REFERENCES tracked_pages(id),
    FOREIGN KEY (group_id) REFERENCES product_groups(group_id)
);
"""

# Indexes for product_groups
CREATE_PRODUCT_GROUPS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_group_name ON product_groups(name);",
]

# Indexes for page_groups (junction table)
CREATE_PAGE_GROUPS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_page_groups_group ON page_groups(group_id);",
    "CREATE INDEX IF NOT EXISTS idx_page_groups_page ON page_groups(page_id);",
]

# Additional indexes for optimizing group aggregation queries
CREATE_AGGREGATION_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_snapshots_url_time ON page_snapshots(url, scraped_at DESC);",
]

# View for latest prices per group (materialized aggregation)
CREATE_LATEST_GROUP_PRICES_VIEW = """
CREATE OR REPLACE VIEW v_latest_group_prices AS
WITH latest_snapshots AS (
    SELECT
        ps.*,
        ROW_NUMBER() OVER (PARTITION BY ps.url ORDER BY ps.scraped_at DESC) as rn
    FROM page_snapshots ps
)
SELECT
    pg.group_id,
    g.name as group_name,
    g.description as group_description,
    g.category,
    g.weekly_usage,
    g.meal_type,
    g.tags,
    tp.id as page_id,
    tp.url,
    tp.provider,
    ls.name as product_name,
    ls.brand,
    ls.sku,
    ls.current_price,
    ls.original_price,
    ls.currency,
    ls.has_promotion,
    ls.discount_percentage,
    ls.promotion_text,
    ls.availability,
    ls.image_url,
    ls.scraped_at
FROM product_groups g
INNER JOIN page_groups pg ON g.group_id = pg.group_id
INNER JOIN tracked_pages tp ON pg.page_id = tp.id
LEFT JOIN latest_snapshots ls ON tp.url = ls.url AND ls.rn = 1
WHERE tp.enabled = TRUE;
"""

# View for basket comparison (total cost per store)
CREATE_BASKET_COMPARISON_VIEW = """
CREATE OR REPLACE VIEW v_basket_comparison AS
SELECT
    provider,
    COUNT(DISTINCT group_id) as products_tracked,
    SUM(current_price) as total_basket_cost,
    ROUND(AVG(current_price), 2) as avg_product_price,
    SUM(CASE WHEN has_promotion THEN 1 ELSE 0 END) as promotions_count,
    SUM(CASE WHEN availability THEN 1 ELSE 0 END) as available_count
FROM v_latest_group_prices
WHERE current_price IS NOT NULL
GROUP BY provider
ORDER BY total_basket_cost ASC;
"""

# View for category-based price analysis
CREATE_CATEGORY_PRICES_VIEW = """
CREATE OR REPLACE VIEW v_category_prices AS
SELECT
    category,
    provider,
    COUNT(*) as product_count,
    ROUND(AVG(current_price), 2) as avg_price,
    ROUND(MIN(current_price), 2) as min_price,
    ROUND(MAX(current_price), 2) as max_price,
    SUM(current_price) as category_total
FROM v_latest_group_prices
WHERE category IS NOT NULL AND current_price IS NOT NULL
GROUP BY category, provider
ORDER BY category, avg_price;
"""

# View for weekly cost estimation
CREATE_WEEKLY_COST_VIEW = """
CREATE OR REPLACE VIEW v_weekly_cost_estimate AS
SELECT
    provider,
    SUM(current_price * COALESCE(weekly_usage, 1)) as estimated_weekly_cost,
    COUNT(*) as products_tracked,
    SUM(weekly_usage) as total_weekly_items
FROM v_latest_group_prices
WHERE current_price IS NOT NULL
GROUP BY provider
ORDER BY estimated_weekly_cost ASC;
"""

# View for best deals (products with largest savings)
CREATE_BEST_DEALS_VIEW = """
CREATE OR REPLACE VIEW v_best_deals AS
WITH price_stats AS (
    SELECT
        group_id,
        group_name,
        category,
        MIN(current_price) as lowest_price,
        MAX(current_price) as highest_price,
        MAX(current_price) - MIN(current_price) as price_difference
    FROM v_latest_group_prices
    WHERE current_price IS NOT NULL
    GROUP BY group_id, group_name, category
)
SELECT
    ps.group_name,
    ps.category,
    lgp.provider as cheapest_at,
    lgp.current_price as best_price,
    ps.highest_price as regular_price,
    ps.price_difference as potential_savings,
    ROUND((ps.price_difference / ps.highest_price) * 100, 1) as savings_percentage,
    lgp.availability,
    lgp.has_promotion
FROM price_stats ps
JOIN v_latest_group_prices lgp
    ON ps.group_id = lgp.group_id
    AND ps.lowest_price = lgp.current_price
WHERE ps.price_difference > 0
ORDER BY ps.price_difference DESC;
"""


# Helper function to get all schema creation statements
def get_schema_statements() -> list[str]:
    statements: list[str] = []

    statements.extend(CREATE_SEQUENCES)
    statements.append(CREATE_PAGE_SNAPSHOTS_TABLE)
    statements.append(CREATE_TRACKED_PAGES_TABLE)
    statements.append(CREATE_PRODUCT_GROUPS_TABLE)
    statements.append(CREATE_PAGE_GROUPS_TABLE)

    statements.extend(CREATE_PAGE_SNAPSHOTS_INDEXES)
    statements.extend(CREATE_TRACKED_PAGES_INDEXES)
    statements.extend(CREATE_PRODUCT_GROUPS_INDEXES)
    statements.extend(CREATE_PAGE_GROUPS_INDEXES)
    statements.extend(CREATE_AGGREGATION_INDEXES)

    statements.append(CREATE_LATEST_GROUP_PRICES_VIEW)
    statements.append(CREATE_BASKET_COMPARISON_VIEW)
    statements.append(CREATE_CATEGORY_PRICES_VIEW)
    statements.append(CREATE_WEEKLY_COST_VIEW)
    statements.append(CREATE_BEST_DEALS_VIEW)

    return statements


# Field mappings for easier data insertion
PAGE_SNAPSHOT_FIELDS = [
    # Primary key (returned by SELECT *)
    "snapshot_id",
    "url",
    "provider",
    "name",
    "description",
    "brand",
    "manufacturer",
    "sku",
    "gtin",
    "current_price",
    "original_price",
    "currency",
    "price_per_unit",
    "has_promotion",
    "discount_percentage",
    "promotion_text",
    "promotion_ends_at",
    "availability",
    "stock_quantity",
    "availability_text",
    "max_order_quantity",
    "short_description",
    "features",
    "category",
    "tags",
    "image_url",
    "images",
    "rating",
    "rating_count",
    "review_count",
    "weight",
    "dimensions",
    "volume",
    "color",
    "size",
    "amount_value",
    "amount_unit",
    "pack_quantity",
    "variant_color",
    "variant_flavor",
    "variant_type",
    "ingredients",
    "nutrition_info",
    "allergens",
    "dietary_info",
    "shipping_cost",
    "free_shipping",
    "delivery_time",
    "extraction_method",
    "structured_data",
    "scraped_at",
]

TRACKED_PAGE_FIELDS = [
    "url",
    "provider",
    "enabled",
    "last_checked",
    "last_price",
    "created_at",
    "updated_at",
]

PRODUCT_GROUP_FIELDS = [
    "group_id",
    "name",
    "slug",
    "description",
    "category",
    "weekly_usage",
    "meal_type",
    "tags",
    "created_at",
    "updated_at",
]

PAGE_GROUP_FIELDS = [
    "page_id",
    "group_id",
    "added_at",
]


# Migration helper for existing databases
MIGRATION_ADD_METADATA_FIELDS = """
-- Add metadata fields to product_groups table (for existing databases)
ALTER TABLE product_groups ADD COLUMN IF NOT EXISTS category VARCHAR(50);
ALTER TABLE product_groups ADD COLUMN IF NOT EXISTS weekly_usage DOUBLE;
ALTER TABLE product_groups ADD COLUMN IF NOT EXISTS meal_type VARCHAR(50);
ALTER TABLE product_groups ADD COLUMN IF NOT EXISTS tags TEXT;
"""


def get_migration_statements() -> list[str]:
    """Get migration statements for upgrading existing databases."""
    return [MIGRATION_ADD_METADATA_FIELDS]
