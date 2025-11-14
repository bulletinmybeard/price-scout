from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.database.db_manager import DatabaseManager
from src.price_tracker.comparator import PriceComparator


@pytest.fixture
def setup_test_data(tmp_path: Path) -> tuple[DatabaseManager, int, str, str]:
    """Create test database with sample data using current schema."""
    test_db = tmp_path / "test.duckdb"
    manager = DatabaseManager(db_path=str(test_db), read_only=False)
    manager.create_tables()

    group_id = manager.create_group(
        name="Test Product Group",
        description="A group for testing price comparison",
    )

    url1 = "https://storea.com/test-product"
    url2 = "https://storeb.com/test-product"

    page1_id = manager.add_tracked_page(
        {
            "url": url1,
            "provider": "store_a",
            "enabled": True,
            "last_checked": datetime.now(UTC),
            "last_price": 99.99,
        }
    )

    page2_id = manager.add_tracked_page(
        {
            "url": url2,
            "provider": "store_b",
            "enabled": True,
            "last_checked": datetime.now(UTC),
            "last_price": 89.99,
        }
    )

    manager.add_page_to_group(page1_id, group_id)
    manager.add_page_to_group(page2_id, group_id)

    manager.add_snapshot(
        {
            "url": url1,
            "provider": "store_a",
            "name": "Test Product",
            "brand": "TestBrand",
            "current_price": 99.99,
            "original_price": 119.99,
            "currency": "EUR",
            "availability": True,
            "availability_text": "In stock",
            "has_promotion": True,
            "discount_percentage": 16.67,
            "sku": "TEST-123",
            "scraped_at": datetime.now(UTC),
        }
    )

    manager.add_snapshot(
        {
            "url": url2,
            "provider": "store_b",
            "name": "Test Product",
            "brand": "TestBrand",
            "current_price": 89.99,
            "original_price": None,
            "currency": "EUR",
            "availability": True,
            "availability_text": "Available",
            "has_promotion": False,
            "discount_percentage": None,
            "sku": "TEST-123",
            "scraped_at": datetime.now(UTC),
        }
    )

    for days_ago in [1, 2, 3, 5, 7]:
        past_date = datetime.now(UTC) - timedelta(days=days_ago)
        manager.add_snapshot(
            {
                "url": url1,
                "provider": "store_a",
                "name": "Test Product",
                "current_price": 99.99 + days_ago,
                "currency": "EUR",
                "availability": True,
                "scraped_at": past_date,
            }
        )

    return manager, group_id, url1, url2


def test_compare_group(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test product group price comparison."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    result = comparator.compare_group("Test Product Group")

    assert "group_name" in result
    assert result["group_name"] == "Test Product Group"
    assert "providers" in result
    assert len(result["providers"]) == 2

    assert "statistics" in result
    stats = result["statistics"]
    assert stats["min_price"] == 89.99
    assert stats["max_price"] == 99.99
    assert stats["avg_price"] == pytest.approx((89.99 + 99.99) / 2, rel=0.01)

    assert "cheapest_provider" in result
    cheapest = result["cheapest_provider"]
    assert cheapest["provider"] == "store_b"
    assert cheapest["current_price"] == 89.99


def test_find_best_deals(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test finding best deals with active promotions."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    deals = comparator.find_best_deals(limit=10, discount_threshold=0.15)

    assert len(deals) >= 1
    assert deals[0]["product_name"] == "Test Product"
    assert deals[0]["provider"] == "store_a"
    assert deals[0]["current_price"] == 99.99
    assert deals[0]["original_price"] == 119.99
    assert deals[0]["discount_percentage"] >= 16.0


def test_get_price_history(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test retrieving price history for a URL."""
    db_manager, _group_id, url1, _url2 = setup_test_data
    comparator = PriceComparator(db_manager)

    history = comparator.get_price_history(url1, days=30)

    assert len(history) >= 6
    assert all("scraped_at" in record for record in history)
    assert all("current_price" in record for record in history)
    assert all("provider" in record for record in history)
    assert all(record["provider"] == "store_a" for record in history)


def test_find_cheapest_in_group(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test finding the cheapest provider in a group."""
    db_manager, _group_id, _url1, url2 = setup_test_data
    comparator = PriceComparator(db_manager)

    cheapest = comparator.find_cheapest_in_group("Test Product Group")

    assert cheapest is not None
    assert cheapest["provider"] == "store_b"
    assert cheapest["current_price"] == 89.99
    assert cheapest["url"] == url2


def test_get_group_statistics(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test getting statistics for a product group."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    stats = comparator.get_group_statistics("Test Product Group")

    assert stats is not None
    assert stats["total_count"] == 2
    assert stats["available_count"] == 2
    assert stats["min_price"] == 89.99
    assert stats["max_price"] == 99.99
    assert stats["avg_price"] == pytest.approx((89.99 + 99.99) / 2, rel=0.01)
    assert stats["price_spread"] == pytest.approx(10.0, rel=0.01)


def test_get_all_groups_summary(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test getting summary for all product groups."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    summaries = comparator.get_all_groups_summary()

    assert len(summaries) >= 1
    summary = summaries[0]
    assert summary["group_name"] == "Test Product Group"
    assert summary["page_count"] == 2
    assert "statistics" in summary
    assert "cheapest_provider" in summary
    assert summary["cheapest_provider"]["provider"] == "store_b"


def test_get_group_price_history(setup_test_data: tuple[DatabaseManager, int, str, str]) -> None:
    """Test getting price history for all providers in a group."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    history = comparator.get_group_price_history("Test Product Group", days=30)

    assert len(history) >= 2
    providers = {h["provider"] for h in history}
    assert "store_a" in providers
    assert "store_b" in providers
