from pydantic import ValidationError
import pytest

from src.config.models import AppConfig, ProductGroupConfig, ProductGroupPageConfig


class TestProductGroupPageConfig:
    """Test ProductGroupPageConfig model validation."""

    def test_simple_url_config(self):
        """Test page config with just URL."""
        page = ProductGroupPageConfig(url="https://www.example.com/product")

        assert page.url == "https://www.example.com/product"
        assert page.provider is None

    def test_url_with_provider(self):
        """Test page config with URL and provider."""
        page = ProductGroupPageConfig(url="https://www.example.com/product", provider="store_a")

        assert page.url == "https://www.example.com/product"
        assert page.provider == "store_a"

    def test_empty_url_validation(self):
        """Test that empty URL is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProductGroupPageConfig(url="")

        assert "at least 1 character" in str(exc_info.value).lower()

    def test_no_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProductGroupPageConfig(url="https://www.example.com", extra="field")

        assert "extra inputs are not permitted" in str(exc_info.value).lower()


class TestProductGroupConfig:
    """Test ProductGroupConfig model validation."""

    def test_minimal_group_config(self):
        """Test group with just name (minimal required field)."""
        group = ProductGroupConfig(name="Test Group")

        assert group.name == "Test Group"
        assert group.description == ""
        assert group.category is None
        assert group.pages == []

    def test_full_group_config(self):
        """Test group with all fields."""
        group = ProductGroupConfig(
            name="Coffee Beans",
            description="Track coffee prices",
            category="groceries",
            pages=["https://www.store-b.example/product1", "https://www.store-a.example/product2"],
        )

        assert group.name == "Coffee Beans"
        assert group.description == "Track coffee prices"
        assert group.category == "groceries"
        assert len(group.pages) == 2

    def test_pages_with_string_urls(self):
        """Test pages as simple string URLs."""
        group = ProductGroupConfig(
            name="Test", pages=["https://www.example.com/1", "https://www.example.com/2"]
        )

        assert len(group.pages) == 2
        assert group.pages[0] == "https://www.example.com/1"
        assert group.pages[1] == "https://www.example.com/2"

    def test_pages_with_dict_format(self):
        """Test pages as dict with url + provider."""
        group = ProductGroupConfig(
            name="Test",
            pages=[
                {"url": "https://www.example.com/1", "provider": "store_a"},
                {"url": "https://www.example.com/2", "provider": "store_b"},
            ],
        )

        assert len(group.pages) == 2
        assert isinstance(group.pages[0], ProductGroupPageConfig)
        assert group.pages[0].url == "https://www.example.com/1"
        assert group.pages[0].provider == "store_a"

    def test_pages_mixed_string_and_dict(self):
        """Test pages with mixed string and dict formats."""
        group = ProductGroupConfig(
            name="Test",
            pages=[
                "https://www.example.com/1",
                {"url": "https://www.example.com/2", "provider": "store_a"},
            ],
        )

        assert len(group.pages) == 2
        assert isinstance(group.pages[0], str)
        assert isinstance(group.pages[1], ProductGroupPageConfig)

    def test_empty_name_validation(self):
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProductGroupConfig(name="")

        assert "at least 1 character" in str(exc_info.value).lower()

    def test_normalize_pages_validator(self):
        """Test that normalize_pages validator handles various inputs."""
        group1 = ProductGroupConfig(name="Test", pages=["https://www.example.com"])
        assert len(group1.pages) == 1

        group2 = ProductGroupConfig(name="Test", pages=[])
        assert len(group2.pages) == 0

        group3 = ProductGroupConfig(name="Test", pages=None)
        assert group3.pages == []

    def test_no_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProductGroupConfig(name="Test", unknown_field="value")

        assert "extra inputs are not permitted" in str(exc_info.value).lower()


class TestAppConfigWithProductGroups:
    """Test AppConfig integration with ProductGroupConfig."""

    def test_product_groups_default_empty(self):
        """Test that product_groups defaults to empty list."""
        config = AppConfig(database={"url": ""})

        assert isinstance(config.product_groups, list)
        assert len(config.product_groups) == 0

    def test_single_product_group(self):
        """Test config with single product group."""
        config_data = {
            "database": {"url": ""},
            "product_groups": [
                {
                    "name": "Test Group",
                    "description": "Test description",
                    "pages": ["https://www.example.com/1"],
                }
            ],
        }

        config = AppConfig(**config_data)

        assert len(config.product_groups) == 1
        assert isinstance(config.product_groups[0], ProductGroupConfig)
        assert config.product_groups[0].name == "Test Group"

    def test_multiple_product_groups(self):
        """Test config with multiple product groups."""
        config_data = {
            "database": {"url": ""},
            "product_groups": [
                {"name": "Group 1", "pages": ["https://www.example.com/1"]},
                {"name": "Group 2", "pages": ["https://www.example.com/2"]},
            ],
        }

        config = AppConfig(**config_data)

        assert len(config.product_groups) == 2
        assert config.product_groups[0].name == "Group 1"
        assert config.product_groups[1].name == "Group 2"

    def test_product_groups_with_mixed_page_formats(self):
        """Test product groups with both string and dict page formats."""
        config_data = {
            "database": {"url": ""},
            "product_groups": [
                {
                    "name": "Mixed Group",
                    "pages": [
                        "https://www.example.com/1",
                        {"url": "https://www.example.com/2", "provider": "store_a"},
                    ],
                }
            ],
        }

        config = AppConfig(**config_data)

        group = config.product_groups[0]
        assert len(group.pages) == 2
        assert isinstance(group.pages[0], str)
        assert isinstance(group.pages[1], ProductGroupPageConfig)

    def test_full_config_all_phases_with_product_groups(self):
        """Test complete config with all 5 phases including product groups."""
        config_data = {
            "database": {"url": "./test.duckdb"},
            "scraping": {"headless": False},
            "providers": {
                "store_a": {
                    "name": "store_a",
                    "country": "NL",
                    "base_url": "https://www.store-a.example",
                }
            },
            "cli": {"max_parallel_urls": 50},
            "product_groups": [
                {
                    "name": "Coffee Beans",
                    "description": "Track coffee prices",
                    "category": "groceries",
                    "pages": [
                        "https://www.store-b.example/producten/product/wi123456",
                        {"url": "https://www.webshop-a/products/coffee", "provider": "store_a"},
                    ],
                }
            ],
        }

        config = AppConfig(**config_data)

        assert config.database.url == "./test.duckdb"
        assert config.scraping.headless is False
        assert "store_a" in config.providers
        assert config.cli.max_parallel_urls == 50
        assert len(config.product_groups) == 1
        assert config.product_groups[0].name == "Coffee Beans"
        assert len(config.product_groups[0].pages) == 2
