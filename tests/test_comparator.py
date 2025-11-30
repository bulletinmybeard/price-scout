from datetime import UTC, datetime, timedelta

import pytest

from src.database.db_manager import DatabaseManager
from src.price_tracker.comparator import PriceComparator


@pytest.fixture
def setup_test_data(tmp_path):
    """Create test database with sample data using current schema."""
    # Use a temporary file database instead of :memory:
    # This works better with the get_connection() context manager approach
    test_db = tmp_path / "test.duckdb"
    # Create in write mode for tests (read_only=False)
    manager = DatabaseManager(db_path=str(test_db), read_only=False)
    manager.create_tables()

    # Create a product group
    group_id = manager.create_group(
        name="Test Product Group",
        description="A group for testing price comparison",
    )

    # Add tracked pages (URLs) to the group
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

    # Add pages to group
    manager.add_page_to_group(page1_id, group_id)
    manager.add_page_to_group(page2_id, group_id)

    # Create snapshots (price history)
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

    # Add historical snapshots for price history testing
    for days_ago in [1, 2, 3, 5, 7]:
        past_date = datetime.now(UTC) - timedelta(days=days_ago)
        manager.add_snapshot(
            {
                "url": url1,
                "provider": "store_a",
                "name": "Test Product",
                "current_price": 99.99 + days_ago,  # Varying prices
                "currency": "EUR",
                "availability": True,
                "scraped_at": past_date,
            }
        )

    return manager, group_id, url1, url2


def test_compare_group(setup_test_data):
    """Test product group price comparison."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    result = comparator.compare_group("Test Product Group")

    # Verify group comparison structure
    assert "group_name" in result
    assert result["group_name"] == "Test Product Group"
    assert "providers" in result
    assert len(result["providers"]) == 2

    # Verify statistics
    assert "statistics" in result
    stats = result["statistics"]
    assert stats["min_price"] == 89.99
    assert stats["max_price"] == 99.99
    assert stats["avg_price"] == pytest.approx((89.99 + 99.99) / 2, rel=0.01)

    # Verify cheapest provider
    assert "cheapest_provider" in result
    cheapest = result["cheapest_provider"]
    assert cheapest["provider"] == "store_b"
    assert cheapest["current_price"] == 89.99


def test_find_best_deals(setup_test_data):
    """Test finding best deals with active promotions."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    # Find deals with discount threshold of 15%
    deals = comparator.find_best_deals(limit=10, discount_threshold=0.15)

    # Should find the store_a product with 16.67% discount
    assert len(deals) >= 1
    assert deals[0]["product_name"] == "Test Product"
    assert deals[0]["provider"] == "store_a"
    assert deals[0]["current_price"] == 99.99
    assert deals[0]["original_price"] == 119.99
    assert deals[0]["discount_percentage"] >= 16.0


def test_get_price_history(setup_test_data):
    """Test retrieving price history for a URL."""
    db_manager, _group_id, url1, _url2 = setup_test_data
    comparator = PriceComparator(db_manager)

    # Get price history for url1 (should have 6 snapshots: 1 current + 5 historical)
    history = comparator.get_price_history(url1, days=30)

    assert len(history) >= 6
    # Verify snapshot structure
    assert all("scraped_at" in record for record in history)
    assert all("current_price" in record for record in history)
    assert all("provider" in record for record in history)
    assert all(record["provider"] == "store_a" for record in history)


def test_find_cheapest_in_group(setup_test_data):
    """Test finding the cheapest provider in a group."""
    db_manager, _group_id, _url1, url2 = setup_test_data
    comparator = PriceComparator(db_manager)

    # Find cheapest in group
    cheapest = comparator.find_cheapest_in_group("Test Product Group")

    assert cheapest is not None
    assert cheapest["provider"] == "store_b"
    assert cheapest["current_price"] == 89.99
    assert cheapest["url"] == url2


def test_get_group_statistics(setup_test_data):
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


def test_get_all_groups_summary(setup_test_data):
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


def test_get_group_price_history(setup_test_data):
    """Test getting price history for all providers in a group."""
    db_manager, *_ = setup_test_data
    comparator = PriceComparator(db_manager)

    history = comparator.get_group_price_history("Test Product Group", days=30)

    # Should have snapshots from both providers
    assert len(history) >= 2
    providers = {h["provider"] for h in history}
    assert "store_a" in providers
    assert "store_b" in providers


class TestBasketComparison:
    """Test basket comparison across multiple product groups."""

    def test_basket_comparison_two_groups_two_providers(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        _setup_basket_test_data(
            db_manager,
            groups=[
                {
                    "name": "Coffee",
                    "category": "beverages",
                    "products": [
                        {"provider": "store_a", "price": 5.99, "name": "Test Coffee"},
                        {"provider": "store_b", "price": 6.49, "name": "Test Coffee"},
                    ],
                },
                {
                    "name": "Milk",
                    "category": "dairy",
                    "products": [
                        {"provider": "store_a", "price": 1.29, "name": "Test Milk"},
                        {"provider": "store_b", "price": 1.35, "name": "Test Milk"},
                    ],
                },
            ],
        )

        result = comparator.compare_baskets(group_names=["Coffee", "Milk"])

        assert len(result["providers"]) == 2
        store_a_total = next(p for p in result["providers"] if p["provider"] == "store_a")
        store_b_total = next(p for p in result["providers"] if p["provider"] == "store_b")

        assert store_a_total["total_cost"] == 7.28  # 5.99 + 1.29
        assert store_b_total["total_cost"] == 7.84  # 6.49 + 1.35
        assert store_a_total["product_count"] == 2
        assert store_b_total["product_count"] == 2

        assert len(result["products"]) == 4  # 2 groups x 2 providers
        assert len(result["categories"]) == 4  # 2 categories x 2 providers

        assert result["statistics"]["total_groups"] == 2
        assert result["statistics"]["total_products"] == 2
        assert result["statistics"]["providers_compared"] == 2
        assert result["statistics"]["price_ranges"]["min"]["provider"] == "store_a"
        assert result["statistics"]["price_ranges"]["difference"] == 0.56

        assert result["missing_groups"] == []

    def test_basket_comparison_three_groups(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        _setup_basket_test_data(
            db_manager,
            groups=[
                {
                    "name": "Coffee",
                    "category": "beverages",
                    "products": [
                        {"provider": "store_a", "price": 5.99},
                        {"provider": "store_b", "price": 6.49},
                    ],
                },
                {
                    "name": "Milk",
                    "category": "dairy",
                    "products": [
                        {"provider": "store_a", "price": 1.29},
                        {"provider": "store_b", "price": 1.35},
                    ],
                },
                {
                    "name": "Bread",
                    "category": "bakery",
                    "products": [
                        {"provider": "store_a", "price": 2.50},
                        {"provider": "store_b", "price": 2.30},  # Store B cheaper on this item
                    ],
                },
            ],
        )

        result = comparator.compare_baskets(group_names=["Coffee", "Milk", "Bread"])

        store_a_total = next(p for p in result["providers"] if p["provider"] == "store_a")
        store_b_total = next(p for p in result["providers"] if p["provider"] == "store_b")

        assert store_a_total["total_cost"] == 9.78  # 5.99 + 1.29 + 2.50
        assert store_b_total["total_cost"] == 10.14  # 6.49 + 1.35 + 2.30
        assert result["statistics"]["price_ranges"]["min"]["provider"] == "store_a"

    def test_basket_comparison_with_promotions(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        _setup_basket_test_data(
            db_manager,
            groups=[
                {
                    "name": "Coffee",
                    "category": "beverages",
                    "products": [
                        {"provider": "store_a", "price": 5.99, "is_promotion": True},
                        {"provider": "store_b", "price": 6.49, "is_promotion": False},
                    ],
                },
                {
                    "name": "Milk",
                    "category": "dairy",
                    "products": [
                        {"provider": "store_a", "price": 1.29, "is_promotion": True},
                        {"provider": "store_b", "price": 1.35, "is_promotion": True},
                    ],
                },
            ],
        )

        result = comparator.compare_baskets(group_names=["Coffee", "Milk"])

        assert result["statistics"]["promotion_count"]["store_a"] == 2
        assert result["statistics"]["promotion_count"]["store_b"] == 1

    def test_basket_comparison_shows_unavailable_but_excludes_from_total(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        _setup_basket_test_data(
            db_manager,
            groups=[
                {
                    "name": "Coffee",
                    "category": "beverages",
                    "products": [
                        {"provider": "store_a", "price": 5.99, "is_available": True},
                        {
                            "provider": "store_b",
                            "price": 6.49,
                            "is_available": False,
                        },  # Unavailable
                    ],
                }
            ],
        )

        result = comparator.compare_baskets(group_names=["Coffee"])

        assert len(result["providers"]) == 2
        assert len(result["products"]) == 2

        store_a_total = next(p for p in result["providers"] if p["provider"] == "store_a")
        store_b_total = next(p for p in result["providers"] if p["provider"] == "store_b")

        assert store_a_total["total_cost"] == 5.99  # Available product included
        assert store_b_total["total_cost"] == 0.00  # Unavailable product excluded from total
        assert store_b_total["available_count"] == 0  # No available products at store_b
        assert store_b_total["product_count"] == 1  # But product still tracked

    def test_basket_comparison_missing_groups(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        _setup_basket_test_data(
            db_manager,
            groups=[
                {
                    "name": "Coffee",
                    "category": "beverages",
                    "products": [{"provider": "store_a", "price": 5.99}],
                }
            ],
        )

        result = comparator.compare_baskets(group_names=["Coffee", "NonExistent", "AlsoMissing"])

        assert len(result["providers"]) == 1  # Only Coffee data
        assert set(result["missing_groups"]) == {"NonExistent", "AlsoMissing"}

    def test_basket_comparison_empty_groups_list_raises_error(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        with pytest.raises(ValueError, match="At least 1 product group required"):
            comparator.compare_baskets(group_names=[])

    def test_basket_comparison_category_subtotals(self, tmp_path):
        db_path = tmp_path / "test_basket.duckdb"
        db_manager = DatabaseManager(db_path=str(db_path), read_only=False)
        db_manager.create_tables()
        comparator = PriceComparator(db_manager)

        _setup_basket_test_data(
            db_manager,
            groups=[
                {
                    "name": "Coffee1",
                    "category": "beverages",
                    "products": [{"provider": "store_a", "price": 5.99}],
                },
                {
                    "name": "Coffee2",
                    "category": "beverages",
                    "products": [{"provider": "store_a", "price": 3.50}],  # 2nd beverage
                },
                {
                    "name": "Milk",
                    "category": "dairy",
                    "products": [{"provider": "store_a", "price": 1.29}],
                },
            ],
        )

        result = comparator.compare_baskets(group_names=["Coffee1", "Coffee2", "Milk"])

        categories = result["categories"]
        beverages = next(c for c in categories if c["category"] == "beverages")
        dairy = next(c for c in categories if c["category"] == "dairy")

        assert beverages["subtotal"] == 9.49  # 5.99 + 3.50
        assert beverages["count"] == 2
        assert dairy["subtotal"] == 1.29
        assert dairy["count"] == 1


def _setup_basket_test_data(db_manager: DatabaseManager, groups: list[dict]):
    """Helper to populate test database with basket comparison data."""
    for group in groups:
        group_id = db_manager.create_group(
            name=group["name"],
            description=f"Test group: {group['name']}",
            category=group.get("category", "test"),
        )

        for product in group["products"]:
            url = f"https://{product['provider']}.com/test/{group['name'].lower()}"

            page_data = {
                "url": url,
                "provider": product["provider"],
            }
            page_id = db_manager.add_tracked_page(page_data)

            db_manager.add_page_to_group(page_id=page_id, group_id=group_id)

            snapshot_data = {
                "url": url,  # Must include URL to link to tracked_page
                "name": product.get("name", f"{group['name']} - {product['provider']}"),
                "current_price": product["price"],  # Field is current_price, not price
                "currency": "EUR",
                "category": group.get("category", "test"),
                "availability": product.get(
                    "is_available", True
                ),  # Field is availability, not is_available
                "has_promotion": product.get(
                    "is_promotion", False
                ),  # Field is has_promotion, not is_promotion
                "provider": product["provider"],
                "scraped_at": datetime.now(UTC),  # Required field
            }
            db_manager.add_snapshot(snapshot_data)
