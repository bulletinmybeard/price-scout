from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
from threading import Lock
from typing import Any

from chalkbox.logging.bridge import get_logger
import duckdb

from src.config.config_loader import load_typed_config
from src.database.models import (
    PAGE_SNAPSHOT_FIELDS,
    PRODUCT_GROUP_FIELDS,
    TRACKED_PAGE_FIELDS,
    get_schema_statements,
)
from src.utils.datetime_utils import now_in_configured_tz
from src.utils.slug import generate_slug

logger = get_logger(__name__)

# Global lock for Parquet export to prevent race conditions when multiple threads export simultaneously
_parquet_export_lock = Lock()


class DatabaseManager:
    """Manages DuckDB database connections and operations for the price tracker."""

    def __init__(self, db_path: str = "./data/price_scout.duckdb", read_only: bool = True):
        self.db_path = Path(db_path)
        self.read_only = read_only
        self.conn = None
        logger.debug(f"Database manager initialized with path: {db_path} (read_only={read_only})")

    def connect(self):
        if self.conn is None:
            self.conn = duckdb.connect(str(self.db_path), read_only=self.read_only)
            logger.debug(f"Connected to database: {self.db_path}")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("Database connection closed")

    @contextmanager
    def get_connection(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        conn = duckdb.connect(str(self.db_path), read_only=self.read_only)
        try:
            yield conn
        except Exception as e:
            # Don't log foreign key constraint errors here - let the caller handle them
            # They're caught and handled appropriately in methods like update_last_checked()
            if "foreign key constraint" not in str(e).lower():
                logger.error(f"Database error occurred: {e}")
            raise
        finally:
            conn.close()

    def create_tables(self) -> None:
        with self.get_connection() as conn:
            for statement in get_schema_statements():
                conn.execute(statement)
            logger.debug("Database schema created successfully")

    def drop_tables(self) -> None:
        """Drop all database tables. Use with caution!"""
        with self.get_connection() as conn:
            # Drop views first
            conn.execute("DROP VIEW IF EXISTS v_latest_group_prices")
            # Drop tables in reverse order of dependencies
            conn.execute("DROP TABLE IF EXISTS page_groups")
            conn.execute("DROP TABLE IF EXISTS page_snapshots")
            conn.execute("DROP TABLE IF EXISTS tracked_pages")
            conn.execute("DROP TABLE IF EXISTS product_groups")
            # Drop sequences
            conn.execute("DROP SEQUENCE IF EXISTS seq_page_snapshots_id")
            conn.execute("DROP SEQUENCE IF EXISTS seq_tracked_pages_id")
            conn.execute("DROP SEQUENCE IF EXISTS seq_product_groups_id")
            logger.warning("All database tables, views, and sequences dropped")

    def add_snapshot(self, snapshot_data: dict[str, Any]) -> int:
        with self.get_connection() as conn:
            prepared_data = self._prepare_snapshot_data(snapshot_data)
            prepared_data.pop("snapshot_id", None)

            fields = ", ".join(prepared_data.keys())
            placeholders = ", ".join(["?" for _ in prepared_data])

            sql = f"""
                INSERT INTO page_snapshots ({fields})
                VALUES ({placeholders})
                RETURNING snapshot_id
            """  # noqa: S608

            result = conn.execute(sql, list(prepared_data.values())).fetchone()
            snapshot_id: int | None = result[0] if result else None

            url = snapshot_data.get("url")
            logger.debug(
                f"Added snapshot: url={url[:50] if url else 'N/A'}, "
                f"price={snapshot_data.get('current_price')}"
            )
            if snapshot_id is None:
                raise ValueError("Failed to get snapshot_id from database")

            # Export to Parquet after successful write
            self.export_snapshots_to_parquet()

            return snapshot_id

    def export_snapshots_to_parquet(self) -> None:
        """Export all database tables to Parquet files using atomic swap."""
        # Use global lock to ensure only one thread exports at a time
        with _parquet_export_lock:
            try:
                # Load typed config for type-safe access
                config = load_typed_config()

                # Check if Parquet export is enabled (default: True)
                if not config.database.export_to_parquet:
                    return

                # Get Parquet directory from config
                parquet_path = config.database.parquet_path
                parquet_dir = Path(parquet_path).parent
                parquet_dir.mkdir(parents=True, exist_ok=True)

                # Tables to export (table_name -> parquet_file_name)
                tables_to_export = {
                    "page_snapshots": "snapshots.parquet",
                    "tracked_pages": "tracked_pages.parquet",
                    "product_groups": "product_groups.parquet",
                    "page_groups": "page_groups.parquet",
                }

                with self.get_connection() as conn:
                    for table_name, parquet_filename in tables_to_export.items():
                        parquet_file = parquet_dir / parquet_filename
                        parquet_tmp = parquet_dir / f"{parquet_file.stem}.tmp{parquet_file.suffix}"

                        # Export to temp file using DuckDB's native Parquet support
                        # Note: table_name comes from internal dictionary keys, not user input
                        sql = (
                            f"COPY (SELECT * FROM {table_name}) TO '{parquet_tmp}' (FORMAT PARQUET)"  # noqa: S608
                        )
                        conn.execute(sql)

                        # Atomic rename - UI never sees partial data
                        parquet_tmp.rename(parquet_file)

                logger.debug(f"Exported all tables to Parquet: {parquet_dir}")

            except Exception as e:
                logger.warning(f"Failed to export tables to Parquet: {e}")
                # Non-fatal - don't break snapshot write if Parquet export fails

    def get_latest_snapshot(self, url: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            sql = """
                SELECT *
                FROM page_snapshots
                WHERE url = ?
                ORDER BY scraped_at DESC
                LIMIT 1
            """
            result = conn.execute(sql, [url]).fetchone()
            return self._row_to_snapshot_dict(result) if result else None

    def get_previous_snapshot(
        self, url: str, before: datetime | None = None
    ) -> dict[str, Any] | None:
        before = before or now_in_configured_tz()

        with self.get_connection() as conn:
            sql = """
                SELECT *
                FROM page_snapshots
                WHERE url = ? AND scraped_at < ?
                ORDER BY scraped_at DESC
                LIMIT 1
            """
            result = conn.execute(sql, [url, before]).fetchone()
            return self._row_to_snapshot_dict(result) if result else None

    def get_snapshot_history(
        self, url: str, days: int = 30, limit: int | None = None
    ) -> list[dict[str, Any]]:
        since = now_in_configured_tz() - timedelta(days=days)

        with self.get_connection() as conn:
            sql = """
                SELECT *
                FROM page_snapshots
                WHERE url = ? AND scraped_at >= ?
                ORDER BY scraped_at DESC
            """
            if limit:
                sql += f" LIMIT {limit}"

            results = conn.execute(sql, [url, since]).fetchall()
            snapshots = [self._row_to_snapshot_dict(row) for row in results]
            return [s for s in snapshots if s is not None]

    def get_snapshots_by_provider(self, provider: str, days: int = 7) -> list[dict[str, Any]]:
        """Get recent snapshots for a specific provider."""
        since = now_in_configured_tz() - timedelta(days=days)

        with self.get_connection() as conn:
            sql = """
                SELECT *
                FROM page_snapshots
                WHERE provider = ? AND scraped_at >= ?
                ORDER BY scraped_at DESC
            """
            results = conn.execute(sql, [provider, since]).fetchall()
            snapshots = [self._row_to_snapshot_dict(row) for row in results]
            return [s for s in snapshots if s is not None]

    def get_snapshot_history_batch(
        self, urls: list[str], limit_per_url: int = 3
    ) -> dict[str, list[dict[str, Any]]]:
        """Get last N snapshots for multiple URLs."""
        if not urls:
            return {}

        with self.get_connection() as conn:
            # Use window function to limit results per URL
            placeholders = ", ".join(["?" for _ in urls])
            sql = f"""
                WITH ranked_snapshots AS (
                    SELECT *,
                           ROW_NUMBER() OVER (PARTITION BY url ORDER BY scraped_at DESC) as rn
                    FROM page_snapshots
                    WHERE url IN ({placeholders})
                )
                SELECT *
                FROM ranked_snapshots
                WHERE rn <= ?
                ORDER BY url, scraped_at DESC
            """  # noqa: S608

            params = [*urls, limit_per_url]
            results = conn.execute(sql, params).fetchall()

            # Group results by URL
            snapshots_by_url: dict[str, list[dict[str, Any]]] = {}
            for row in results:
                snapshot = self._row_to_snapshot_dict(row)
                if snapshot is None:
                    continue
                url = snapshot["url"]
                if url not in snapshots_by_url:
                    snapshots_by_url[url] = []
                snapshots_by_url[url].append(snapshot)

            return snapshots_by_url

    def get_latest_snapshots_with_previous(
        self, urls: list[str]
    ) -> dict[str, dict[str, dict[str, Any] | None]]:
        """Get latest snapshot + previous snapshot for each URL to detect changes."""
        with self.get_connection() as conn:
            # Use window function to rank snapshots per URL
            placeholders = ", ".join(["?"] * len(urls))
            # Note: placeholders are constructed from internal list length, not user input
            sql = f"""
                WITH ranked_snapshots AS (
                    SELECT *,
                           ROW_NUMBER() OVER (PARTITION BY url ORDER BY scraped_at DESC) as rn
                    FROM page_snapshots
                    WHERE url IN ({placeholders})
                )
                SELECT *
                FROM ranked_snapshots
                WHERE rn <= 2
                ORDER BY url, scraped_at DESC
            """  # noqa: S608

            cursor = conn.execute(sql, urls)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            # Organize results by URL
            result: dict[str, dict[str, dict[str, Any] | None]] = {}

            for url in urls:
                result[url] = {"latest": None, "previous": None}

            # Process rows - first row per URL is latest, second is previous
            for row in rows:
                row_dict = dict(zip(columns, row, strict=True))
                url = row_dict["url"]

                if result[url]["latest"] is None:
                    result[url]["latest"] = row_dict
                elif result[url]["previous"] is None:
                    result[url]["previous"] = row_dict

            return result

    def add_tracked_page(self, page_data: dict[str, Any]) -> int:
        """
        Add a tracked page to the database (only if it doesn't exist yet).

        Returns the page ID (auto-generated for new pages, existing ID if already tracked).

        Note: If the page already exists, this method returns the existing ID without
        updating any fields. This prevents foreign key constraint errors when pages
        are already associated with product groups. Use update_last_checked() to update
        timestamps on existing pages.

        Example:
            page_id = db_manager.add_tracked_page({
                'url': 'https://...',
                'provider': 'webshop-a',
                'enabled': True,
                'last_checked': now_in_configured_tz(),
                'last_price': 9.99
            })
        """
        with self.get_connection() as conn:
            url = page_data.get("url")

            # First, check if the page already exists
            existing = conn.execute("SELECT id FROM tracked_pages WHERE url = ?", [url]).fetchone()

            if existing:
                # Page already exists - just return the existing ID
                existing_id: int = existing[0]
                logger.debug(f"Tracked page already exists: {url[:50] if url else 'N/A'}")
                return existing_id

            # Page doesn't exist - insert new record
            page_data.pop("id", None)  # Remove id (auto-generated)
            page_data.setdefault("enabled", True)
            page_data.setdefault("created_at", now_in_configured_tz())
            page_data["updated_at"] = now_in_configured_tz()

            fields = ", ".join(page_data.keys())
            placeholders = ", ".join(["?" for _ in page_data])

            sql = f"""
                INSERT INTO tracked_pages ({fields})
                VALUES ({placeholders})
                RETURNING id
            """  # noqa: S608
            result = conn.execute(sql, list(page_data.values())).fetchone()

            if result is None:
                raise ValueError(f"Failed to insert tracked page for {url}")

            new_id: int = result[0]
            logger.debug(f"Added new tracked page: {url[:50] if url else 'N/A'}")
            return new_id

    def get_tracked_page(self, url: str) -> dict[str, Any] | None:
        """Get tracking state for a URL."""
        with self.get_connection() as conn:
            sql = "SELECT * FROM tracked_pages WHERE url = ?"
            result = conn.execute(sql, [url]).fetchone()
            return self._row_to_tracked_page_dict(result) if result else None

    def get_all_tracked_pages(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        """Get all tracked pages."""
        with self.get_connection() as conn:
            sql = "SELECT * FROM tracked_pages"
            if enabled_only:
                sql += " WHERE enabled = TRUE"
            sql += " ORDER BY provider, url"

            results = conn.execute(sql).fetchall()
            pages = [self._row_to_tracked_page_dict(row) for row in results]
            return [p for p in pages if p is not None]

    def update_last_checked(self, url: str, price: float | None = None) -> None:
        """
        Update last_checked timestamp and optionally last_price.

        Note: This method may silently fail if the tracked page is referenced by
        product groups due to foreign key constraints. This is expected behavior
        and does not affect product tracking functionality.
        """
        try:
            with self.get_connection() as conn:
                now = now_in_configured_tz()
                if price is not None:
                    sql = """
                        UPDATE tracked_pages
                        SET last_checked = ?, last_price = ?, updated_at = ?
                        WHERE url = ?
                    """
                    conn.execute(sql, [now, price, now, url])
                else:
                    sql = """
                        UPDATE tracked_pages
                        SET last_checked = ?, updated_at = ?
                        WHERE url = ?
                    """
                    conn.execute(sql, [now, now, url])
        except Exception as e:
            # Silently ignore foreign key constraint errors
            # These occur when pages are referenced by product groups
            if "foreign key constraint" not in str(e).lower():
                # Re-raise if it's not a foreign key error
                raise
            logger.debug(f"Skipped update for {url[:50]} (referenced by product group)")

    def get_price_trend(self, url: str, days: int = 30) -> list[dict[str, Any]]:
        """Calculate price trend over time."""
        since = now_in_configured_tz() - timedelta(days=days)

        with self.get_connection() as conn:
            sql = """
                SELECT
                    DATE_TRUNC('day', scraped_at) as date,
                    AVG(current_price) as avg_price,
                    MIN(current_price) as min_price,
                    MAX(current_price) as max_price,
                    BOOL_OR(has_promotion) as had_promotion
                FROM page_snapshots
                WHERE url = ? AND scraped_at >= ?
                GROUP BY DATE_TRUNC('day', scraped_at)
                ORDER BY date
            """
            results = conn.execute(sql, [url, since]).fetchall()

            return [
                {
                    "date": row[0],
                    "avg_price": row[1],
                    "min_price": row[2],
                    "max_price": row[3],
                    "had_promotion": row[4],
                }
                for row in results
            ]

    def get_active_promotions(self, provider: str | None = None) -> list[dict[str, Any]]:
        """Get all products currently on promotion (from latest snapshots)."""
        with self.get_connection() as conn:
            # Get latest snapshot per URL
            sql = """
                WITH latest_snapshots AS (
                    SELECT
                        url,
                        MAX(scraped_at) as latest_scraped
                    FROM page_snapshots
                    """
            params = []

            if provider:
                sql += " WHERE provider = ?"
                params.append(provider)

            sql += """
                    GROUP BY url
                )
                SELECT ps.*
                FROM page_snapshots ps
                INNER JOIN latest_snapshots ls
                    ON ps.url = ls.url AND ps.scraped_at = ls.latest_scraped
                WHERE ps.has_promotion = TRUE
                ORDER BY ps.discount_percentage DESC
            """

            results = conn.execute(sql, params).fetchall()
            snapshots = [self._row_to_snapshot_dict(row) for row in results]
            return [s for s in snapshots if s is not None]

    def get_price_statistics(self, url: str, days: int = 90) -> dict[str, Any]:
        """Calculate price statistics for a product."""
        since = now_in_configured_tz() - timedelta(days=days)

        with self.get_connection() as conn:
            sql = """
                SELECT
                    MIN(current_price) as min_price,
                    MAX(current_price) as max_price,
                    AVG(current_price) as avg_price,
                    COUNT(*) as snapshot_count
                FROM page_snapshots
                WHERE url = ? AND scraped_at >= ?
            """
            stats = conn.execute(sql, [url, since]).fetchone()

            if stats is None:
                return {
                    "url": url,
                    "min_price": None,
                    "max_price": None,
                    "avg_price": None,
                    "current_price": None,
                    "snapshot_count": 0,
                    "days": days,
                }

            # Get latest price
            latest = self.get_latest_snapshot(url)

            return {
                "url": url,
                "min_price": stats[0],
                "max_price": stats[1],
                "avg_price": stats[2],
                "current_price": latest.get("current_price") if latest else None,
                "snapshot_count": stats[3],
                "days": days,
            }

    # ==================== Product Groups Operations ====================

    def create_group(
        self,
        name: str,
        description: str | None = None,
        category: str | None = None,
        weekly_usage: float | None = None,
        meal_type: str | None = None,
        tags: list[str] | None = None,
    ) -> int:
        """
        Create a new product group with optional metadata.

        Automatically generates a slug from the name for normalized matching.

        Example:
            group_id = db_manager.create_group(
                name="Whole Milk 1L",
                description="Full-fat milk tracking",
                category="dairy",
                weekly_usage=2,
                meal_type="breakfast",
                tags=["essentials", "weekly"]
            )
        """
        # Generate slug from name
        slug = generate_slug(name)

        with self.get_connection() as conn:
            # Check if group already exists (by name or slug)
            existing = conn.execute(
                "SELECT group_id FROM product_groups WHERE name = ? OR slug = ?",
                [name, slug],
            ).fetchone()

            if existing:
                # Group exists, update metadata if provided
                group_id: int = existing[0]
                logger.debug(f"Group '{name}' already exists with ID {group_id}")

                # Update metadata fields if changed
                update_parts: list[str] = []
                params: list[Any] = []

                if description is not None:
                    update_parts.append("description = ?")
                    params.append(description)
                if category is not None:
                    update_parts.append("category = ?")
                    params.append(category)
                if weekly_usage is not None:
                    update_parts.append("weekly_usage = ?")
                    params.append(weekly_usage)
                if meal_type is not None:
                    update_parts.append("meal_type = ?")
                    params.append(meal_type)
                if tags is not None:
                    update_parts.append("tags = ?")
                    params.append(json.dumps(tags))

                if update_parts:
                    update_parts.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(group_id)
                    sql = f"""
                        UPDATE product_groups
                        SET {", ".join(update_parts)}
                        WHERE group_id = ?
                    """  # noqa: S608
                    conn.execute(sql, params)
                    logger.debug(f"Updated metadata for group '{name}'")

                return group_id

            # Create new group with slug
            tags_json = json.dumps(tags) if tags else None
            sql = """
                INSERT INTO product_groups (name, slug, description, category, weekly_usage, meal_type, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING group_id
            """
            result = conn.execute(
                sql,
                [name, slug, description, category, weekly_usage, meal_type, tags_json],
            ).fetchone()
            if result is None:
                raise ValueError(f"Failed to create group '{name}'")
            new_group_id: int = result[0]
            logger.debug(f"Created group '{name}' (slug: {slug}) with ID {new_group_id}")
            return new_group_id

    def get_group_by_name(self, name: str) -> dict[str, Any] | None:
        """Get group by name."""
        with self.get_connection() as conn:
            sql = "SELECT * FROM product_groups WHERE name = ?"
            result = conn.execute(sql, [name]).fetchone()
            return self._row_to_group_dict(result) if result else None

    def get_all_groups(self) -> list[dict[str, Any]]:
        """Get all product groups with page counts."""
        with self.get_connection() as conn:
            sql = """
                SELECT
                    g.*,
                    COUNT(DISTINCT pg.page_id) as page_count
                FROM product_groups g
                LEFT JOIN page_groups pg ON g.group_id = pg.group_id
                GROUP BY g.group_id, g.name, g.slug, g.description, g.category, g.weekly_usage, g.meal_type, g.tags, g.created_at, g.updated_at
                ORDER BY g.name
            """
            results = conn.execute(sql).fetchall()
            groups = [self._row_to_group_dict(row, include_page_count=True) for row in results]
            return [g for g in groups if g is not None]

    def get_all_groups_for_fuzzy_match(self) -> list[dict[str, Any]]:
        """Get all groups with minimal data for fuzzy matching (lightweight).

        Returns only group_id, name, and slug for efficient fuzzy matching.

        Returns:
            List of dicts with keys: group_id, name, slug
        """
        with self.get_connection() as conn:
            sql = "SELECT group_id, name, slug FROM product_groups ORDER BY name"
            results = conn.execute(sql).fetchall()
            return [{"group_id": row[0], "name": row[1], "slug": row[2]} for row in results]

    def add_page_to_group(self, page_id: int, group_id: int) -> None:
        """Link a tracked page to a product group."""
        with self.get_connection() as conn:
            try:
                sql = """
                    INSERT INTO page_groups (page_id, group_id)
                    VALUES (?, ?)
                """
                conn.execute(sql, [page_id, group_id])
                logger.debug(f"Added page {page_id} to group {group_id}")
            except Exception as e:
                # Ignore duplicate key errors (already associated)
                if "UNIQUE" in str(e) or "duplicate" in str(e).lower():
                    logger.debug(f"Page {page_id} already in group {group_id}")
                else:
                    raise

    def remove_page_from_group(self, page_id: int, group_id: int) -> None:
        """Remove a page from a product group."""
        with self.get_connection() as conn:
            sql = "DELETE FROM page_groups WHERE page_id = ? AND group_id = ?"
            conn.execute(sql, [page_id, group_id])
            logger.debug(f"Removed page {page_id} from group {group_id}")

    def get_group_pages(self, group_name: str) -> list[dict[str, Any]]:
        """
        Get all pages in a group with their latest prices.

        NOTE: Uses the v_latest_group_prices view for efficiency.
        """
        with self.get_connection() as conn:
            sql = """
                SELECT * FROM v_latest_group_prices
                WHERE group_name = ?
                ORDER BY provider, product_name
            """
            results = conn.execute(sql, [group_name]).fetchall()
            pages = [self._row_to_group_page_dict(row) for row in results]
            return [p for p in pages if p is not None]

    def get_group_comparison(self, group_name: str) -> dict[str, Any]:
        """Compare prices across providers in a group."""
        pages = self.get_group_pages(group_name)

        if not pages:
            return {
                "group_name": group_name,
                "providers": [],
                "statistics": None,
                "cheapest_provider": None,
            }

        provider_data = {}
        for page in pages:
            provider = page["provider"]
            if provider not in provider_data:
                provider_data[provider] = {
                    "provider": provider,
                    "product_name": page["product_name"],
                    "current_price": page["current_price"],
                    "currency": page.get("currency", "EUR"),
                    "has_promotion": page["has_promotion"],
                    "discount_percentage": page["discount_percentage"],
                    "availability": page["availability"],
                    "url": page["url"],
                    "scraped_at": page["scraped_at"],
                }

        providers = list(provider_data.values())

        # Calculate statistics (only for available products with prices)
        available_prices = [
            p["current_price"]
            for p in providers
            if p["current_price"] is not None and p["availability"]
        ]

        if available_prices:
            min_price = min(available_prices)
            max_price = max(available_prices)
            avg_price = sum(available_prices) / len(available_prices)
            price_spread = max_price - min_price

            # Find the cheapest price
            cheapest = min(
                (p for p in providers if p["current_price"] is not None and p["availability"]),
                key=lambda x: x["current_price"],
            )

            statistics = {
                "min_price": min_price,
                "max_price": max_price,
                "avg_price": avg_price,
                "price_spread": price_spread,
                "available_count": len(available_prices),
                "total_count": len(providers),
            }
        else:
            statistics = None
            cheapest = None

        return {
            "group_name": group_name,
            "providers": sorted(providers, key=lambda x: x["current_price"] or float("inf")),
            "statistics": statistics,
            "cheapest_provider": cheapest,
        }

    def get_group_price_history(self, group_name: str, days: int = 30) -> list[dict[str, Any]]:
        """
        Get price history for all providers in a group.

        Returns time-series data with daily aggregations per provider.
        """
        since = now_in_configured_tz() - timedelta(days=days)

        with self.get_connection() as conn:
            # Get historical aggregations grouped by day
            sql = """
                SELECT
                    DATE_TRUNC('day', ps.scraped_at) as date,
                    ps.provider,
                    ps.url,
                    ps.name as product_name,
                    AVG(ps.current_price) as avg_price,
                    MIN(ps.current_price) as min_price,
                    MAX(ps.current_price) as max_price,
                    MAX(ps.scraped_at) as latest_scraped_at,
                    BOOL_OR(ps.has_promotion) as had_promotion,
                    COUNT(*) as snapshot_count
                FROM product_groups g
                INNER JOIN page_groups pg ON g.group_id = pg.group_id
                INNER JOIN tracked_pages tp ON pg.page_id = tp.id
                INNER JOIN page_snapshots ps ON tp.url = ps.url
                WHERE g.name = ? AND ps.scraped_at >= ?
                GROUP BY DATE_TRUNC('day', ps.scraped_at), ps.provider, ps.url, ps.name
                ORDER BY date DESC, ps.provider
            """
            results = conn.execute(sql, [group_name, since]).fetchall()

            return [
                {
                    "date": row[0],
                    "provider": row[1],
                    "url": row[2],
                    "product_name": row[3],
                    "avg_price": row[4],
                    "min_price": row[5],
                    "max_price": row[6],
                    "latest_scraped_at": row[7],
                    "had_promotion": row[8],
                    "snapshot_count": row[9],
                }
                for row in results
            ]

    def get_cheapest_in_group(self, group_name: str) -> dict[str, Any] | None:
        """Find the provider with the lowest current price in a group."""
        comparison = self.get_group_comparison(group_name)
        return comparison.get("cheapest_provider")

    def get_group_statistics(self, group_name: str) -> dict[str, Any] | None:
        """Get statistical summary for a group."""
        comparison = self.get_group_comparison(group_name)
        stats = comparison.get("statistics")
        return stats if isinstance(stats, dict) else None

    # ==================== Utility Methods ====================

    def execute_query(self, sql: str, params: list | None = None) -> list:
        """Execute a custom SQL query."""
        with self.get_connection() as conn:
            result = conn.execute(sql, params or [])
            return result.fetchall()

    @staticmethod
    def _prepare_snapshot_data(data: dict[str, Any]) -> dict[str, Any]:
        """Prepare snapshot data for insertion (handle JSON fields)."""
        prepared: dict[str, Any] = {}

        json_fields = [
            "features",
            "category",
            "tags",
            "images",
            "nutrition_info",
            "allergens",
            "dietary_info",
            "structured_data",
        ]

        for key, value in data.items():
            if value is None:
                prepared[key] = None
            elif key in json_fields:
                # Convert Python objects to JSON strings
                prepared[key] = json.dumps(value) if value else None
            else:
                prepared[key] = value

        return prepared

    @staticmethod
    def _row_to_snapshot_dict(row: tuple) -> dict[str, Any] | None:
        """Convert database row to snapshot dictionary."""
        if not row:
            return None

        # Get column names from page_snapshots
        column_names = PAGE_SNAPSHOT_FIELDS

        snapshot = {}
        for i, col_name in enumerate(column_names):
            if i < len(row):
                value = row[i]
                # Parse JSON fields
                if col_name in [
                    "features",
                    "category",
                    "tags",
                    "images",
                    "nutrition_info",
                    "allergens",
                    "dietary_info",
                    "structured_data",
                ]:
                    # Check for non-empty string before parsing JSON
                    if value and isinstance(value, str) and value.strip():
                        try:
                            snapshot[col_name] = json.loads(value)
                        except json.JSONDecodeError:
                            logger.debug(f"Failed to parse JSON for {col_name}: {value[:100]}")
                            snapshot[col_name] = None
                    elif value is not None and not isinstance(value, str):
                        # Already parsed by DuckDB (dict/list)
                        snapshot[col_name] = value
                    else:
                        snapshot[col_name] = None
                else:
                    snapshot[col_name] = value

        return snapshot

    @staticmethod
    def _row_to_tracked_page_dict(row: tuple) -> dict[str, Any] | None:
        """Convert database row to tracked page dictionary."""
        if not row:
            return None

        column_names = ["id", *TRACKED_PAGE_FIELDS]

        tracked_page = {}
        for i, col_name in enumerate(column_names):
            if i < len(row):
                tracked_page[col_name] = row[i]

        return tracked_page

    @staticmethod
    def _row_to_group_dict(row: tuple, include_page_count: bool = False) -> dict[str, Any] | None:
        """Convert database row to product group dictionary."""
        if not row:
            return None

        column_names = PRODUCT_GROUP_FIELDS.copy()
        if include_page_count:
            column_names.append("page_count")

        group = {}
        for i, col_name in enumerate(column_names):
            if i < len(row):
                group[col_name] = row[i]

        return group

    @staticmethod
    def _row_to_group_page_dict(row: tuple) -> dict[str, Any] | None:
        """Convert database row from v_latest_group_prices view to dictionary."""
        if not row:
            return None

        # Column names from v_latest_group_prices view (including metadata)
        column_names = [
            "group_id",
            "group_name",
            "group_description",
            "category",
            "weekly_usage",
            "meal_type",
            "tags",
            "page_id",
            "url",
            "provider",
            "product_name",
            "brand",
            "sku",
            "current_price",
            "original_price",
            "currency",
            "has_promotion",
            "discount_percentage",
            "promotion_text",
            "availability",
            "image_url",
            "scraped_at",
        ]

        page = {}
        for i, col_name in enumerate(column_names):
            if i < len(row):
                page[col_name] = row[i]

        return page

    @contextmanager
    def session_scope(self):
        """Compatibility method for code using `session_scope` pattern."""
        conn = duckdb.connect(str(self.db_path))
        try:
            yield conn
        except Exception as e:
            logger.error(f"Session error: {e}")
            raise
        finally:
            conn.close()
