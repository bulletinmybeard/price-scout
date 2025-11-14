-- Initialize DuckDB UI with Parquet Data Sources
--
-- The UI reads ONLY from Parquet files to avoid ANY file locking issues.
-- All tables are exported to Parquet by DBManager after each write.
--
-- All views are recreated from Parquet files, allowing complex analytics
-- queries like CTEs, window functions, joins across tables, etc.

-- Create views for all tables from Parquet files
CREATE OR REPLACE VIEW page_snapshots AS
  SELECT * FROM read_parquet('/data/snapshots.parquet');

CREATE OR REPLACE VIEW tracked_pages AS
  SELECT * FROM read_parquet('/data/tracked_pages.parquet');

CREATE OR REPLACE VIEW product_groups AS
  SELECT * FROM read_parquet('/data/product_groups.parquet');

CREATE OR REPLACE VIEW page_groups AS
  SELECT * FROM read_parquet('/data/page_groups.parquet');

-- Recreate analytical views (same as in db_manager.py)
-- These enable pre-built complex queries for common analytics tasks

CREATE OR REPLACE VIEW v_latest_group_prices AS
WITH latest_snapshots AS (
    SELECT
        ps.*,
        ROW_NUMBER() OVER (PARTITION BY ps.url ORDER BY ps.scraped_at DESC) AS rn
    FROM page_snapshots AS ps
)
SELECT
    pg.group_id,
    g.name AS group_name,
    g.description AS group_description,
    g.category,
    g.weekly_usage,
    g.meal_type,
    g.tags,
    tp.id AS page_id,
    tp.url,
    tp.provider,
    ls.name AS product_name,
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
FROM product_groups AS g
INNER JOIN page_groups AS pg ON (g.group_id = pg.group_id)
INNER JOIN tracked_pages AS tp ON (pg.page_id = tp.id)
LEFT JOIN latest_snapshots AS ls ON (tp.url = ls.url AND ls.rn = 1)
WHERE tp.enabled = true;

CREATE OR REPLACE VIEW v_best_deals AS
WITH price_stats AS (
    SELECT
        group_id,
        group_name,
        category,
        MIN(current_price) AS lowest_price,
        MAX(current_price) AS highest_price,
        (MAX(current_price) - MIN(current_price)) AS price_difference
    FROM v_latest_group_prices
    WHERE current_price IS NOT NULL
    GROUP BY group_id, group_name, category
)
SELECT
    ps.group_name,
    ps.category,
    lgp.provider AS cheapest_at,
    lgp.current_price AS best_price,
    ps.highest_price AS regular_price,
    ps.price_difference AS potential_savings,
    ROUND((ps.price_difference / ps.highest_price) * 100, 1) AS savings_percentage,
    lgp.availability,
    lgp.has_promotion
FROM price_stats AS ps
INNER JOIN v_latest_group_prices AS lgp
    ON (ps.group_id = lgp.group_id AND ps.lowest_price = lgp.current_price)
WHERE ps.price_difference > 0
ORDER BY ps.price_difference DESC;

CREATE OR REPLACE VIEW v_category_prices AS
SELECT
    category,
    provider,
    COUNT(*) AS product_count,
    ROUND(AVG(current_price), 2) AS avg_price,
    ROUND(MIN(current_price), 2) AS min_price,
    ROUND(MAX(current_price), 2) AS max_price,
    SUM(current_price) AS category_total
FROM v_latest_group_prices
WHERE category IS NOT NULL AND current_price IS NOT NULL
GROUP BY category, provider
ORDER BY category, avg_price;

CREATE OR REPLACE VIEW v_basket_comparison AS
SELECT
    provider,
    COUNT(DISTINCT group_id) AS products_tracked,
    SUM(current_price) AS total_basket_cost,
    ROUND(AVG(current_price), 2) AS avg_product_price,
    SUM(CASE WHEN has_promotion THEN 1 ELSE 0 END) AS promotions_count,
    SUM(CASE WHEN availability THEN 1 ELSE 0 END) AS available_count
FROM v_latest_group_prices
WHERE current_price IS NOT NULL
GROUP BY provider
ORDER BY total_basket_cost ASC;

CREATE OR REPLACE VIEW v_weekly_cost_estimate AS
SELECT
    provider,
    SUM(current_price * COALESCE(weekly_usage, 1)) AS estimated_weekly_cost,
    COUNT(*) AS products_tracked,
    SUM(weekly_usage) AS total_weekly_items
FROM v_latest_group_prices
WHERE current_price IS NOT NULL
GROUP BY provider
ORDER BY estimated_weekly_cost ASC;

-- Start DuckDB Web UI
-- Note: This actually starts the HTTP server on port 4213
CALL start_ui();
