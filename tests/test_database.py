from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pytest

from src.database.db_manager import DatabaseManager


@pytest.fixture
def db_manager():
    """Create a test database manager with temporary DuckDB file."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
        tmp_path = tmp_file.name
    Path(tmp_path).unlink()  # Delete the empty file so DuckDB can create it fresh

    manager = DatabaseManager(db_path=tmp_path, read_only=False)
    manager.create_tables()
    yield manager

    Path(tmp_path).unlink(missing_ok=True)


def test_snapshot_operations(db_manager):
    """Test CRUD operations for page snapshots."""
    snapshot_data = {
        "url": "https://test.com/product",
        "provider": "test_provider",
        "name": "Test Product",
        "brand": "Test Brand",
        "sku": "TEST-123",
        "current_price": 9.99,
        "currency": "EUR",
        "availability": True,
        "scraped_at": datetime.now(),
    }
    snapshot_id = db_manager.add_snapshot(snapshot_data)

    assert snapshot_id is not None

    retrieved = db_manager.get_latest_snapshot("https://test.com/product")
    assert retrieved["name"] == "Test Product"
    assert retrieved["current_price"] == 9.99

    history = db_manager.get_snapshot_history("https://test.com/product", days=30)
    assert len(history) >= 1


def test_tracked_page_operations(db_manager):
    """Test CRUD operations for tracked pages."""
    page_data = {
        "url": "https://test.com/product",
        "provider": "test_provider",
        "enabled": True,
        "last_price": 9.99,
    }
    page_id = db_manager.add_tracked_page(page_data)

    assert page_id is not None

    retrieved = db_manager.get_tracked_page("https://test.com/product")
    assert retrieved["provider"] == "test_provider"
    assert retrieved["enabled"]

    all_pages = db_manager.get_all_tracked_pages(enabled_only=False)
    assert len(all_pages) >= 1

    db_manager.update_last_checked("https://test.com/product", price=10.99)
    updated = db_manager.get_tracked_page("https://test.com/product")
    assert updated["last_price"] == 10.99


def test_price_history(db_manager):
    """Test price trend analysis."""
    url = "https://test.com/product"

    db_manager.add_tracked_page(
        {
            "url": url,
            "provider": "test_provider",
            "enabled": True,
        }
    )

    for i in range(5):
        snapshot_data = {
            "url": url,
            "provider": "test_provider",
            "name": "Test Product",
            "current_price": 10.0 + i,
            "currency": "EUR",
            "scraped_at": datetime.now() - timedelta(days=4 - i),
        }
        db_manager.add_snapshot(snapshot_data)

    trend = db_manager.get_price_trend(url, days=30)
    assert len(trend) >= 1

    stats = db_manager.get_price_statistics(url, days=30)
    assert stats["min_price"] == 10.0
    assert stats["max_price"] == 14.0
    assert stats["snapshot_count"] == 5


def test_product_groups(db_manager):
    """Test product groups functionality."""
    group_id = db_manager.create_group(name="Test Group", description="Test group for testing")
    assert group_id is not None

    group = db_manager.get_group_by_name("Test Group")
    assert group["name"] == "Test Group"
    assert group["description"] == "Test group for testing"

    page1_id = db_manager.add_tracked_page(
        {
            "url": "https://test1.com/product",
            "provider": "provider1",
            "enabled": True,
        }
    )
    page2_id = db_manager.add_tracked_page(
        {
            "url": "https://test2.com/product",
            "provider": "provider2",
            "enabled": True,
        }
    )

    db_manager.add_page_to_group(page1_id, group_id)
    db_manager.add_page_to_group(page2_id, group_id)

    db_manager.add_snapshot(
        {
            "url": "https://test1.com/product",
            "provider": "provider1",
            "name": "Product A",
            "current_price": 9.99,
            "availability": True,
            "scraped_at": datetime.now(),
        }
    )
    db_manager.add_snapshot(
        {
            "url": "https://test2.com/product",
            "provider": "provider2",
            "name": "Product B",
            "current_price": 12.99,
            "availability": True,
            "scraped_at": datetime.now(),
        }
    )

    pages = db_manager.get_group_pages("Test Group")
    assert len(pages) == 2

    comparison = db_manager.get_group_comparison("Test Group")
    assert comparison["group_name"] == "Test Group"
    assert len(comparison["providers"]) == 2
    assert comparison["statistics"]["min_price"] == 9.99
    assert comparison["statistics"]["max_price"] == 12.99
    assert comparison["cheapest_provider"]["provider"] == "provider1"

    db_manager.remove_page_from_group(page1_id, group_id)
    pages_after = db_manager.get_group_pages("Test Group")
    assert len(pages_after) == 1


def test_promotions(db_manager):
    """Test promotion detection and retrieval."""
    snapshot_data = {
        "url": "https://test.com/product",
        "provider": "test_provider",
        "name": "Promo Product",
        "current_price": 7.99,
        "original_price": 9.99,
        "has_promotion": True,
        "discount_percentage": 20.0,
        "promotion_text": "20% OFF",
        "availability": True,
        "scraped_at": datetime.now(),
    }
    db_manager.add_snapshot(snapshot_data)

    promotions = db_manager.get_active_promotions()
    assert len(promotions) >= 1
    assert promotions[0]["has_promotion"]
    assert promotions[0]["discount_percentage"] == 20.0

    provider_promos = db_manager.get_active_promotions(provider="test_provider")
    assert len(provider_promos) >= 1
