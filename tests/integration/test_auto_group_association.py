from pathlib import Path
import tempfile
from unittest.mock import patch

import yaml

from src.cli.commands.track import auto_associate_with_groups


class TestAutoAssociateWithGroups:
    """Test suite for auto_associate_with_groups function."""

    def test_url_in_single_group(self, temp_config_file, mock_db_manager):
        """Test URL association when URL exists in one group."""
        url = "https://www.webshop-a/products/coffee-500g"

        associated = auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        assert len(associated) == 1
        assert "Coffee - Douwe Egberts" in associated
        mock_db_manager.create_group.assert_called_once()
        mock_db_manager.add_page_to_group.assert_called_once()

    def test_url_in_multiple_groups(self, temp_config_file, mock_db_manager):
        """Test URL association when URL exists in multiple groups."""
        config_data = {
            "database": {"url": ":memory:"},
            "product_groups": [
                {"name": "Group 1", "pages": ["https://www.example.com/product"]},
                {"name": "Group 2", "pages": ["https://www.example.com/product"]},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            multi_config = f.name

        try:
            url = "https://www.example.com/product"
            associated = auto_associate_with_groups(url, mock_db_manager, multi_config)

            assert len(associated) == 2
            assert "Group 1" in associated
            assert "Group 2" in associated
            assert mock_db_manager.create_group.call_count == 2
            assert mock_db_manager.add_page_to_group.call_count == 2
        finally:
            Path(multi_config).unlink()

    def test_url_not_in_any_group(self, temp_config_file, mock_db_manager):
        """Test URL association when URL doesn't exist in any group."""
        url = "https://www.store-e.example/product/not-in-config"

        associated = auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        assert len(associated) == 0
        mock_db_manager.create_group.assert_not_called()
        mock_db_manager.add_page_to_group.assert_not_called()

    def test_dict_format_pages(self, temp_config_file, mock_db_manager):
        """Test URL association with dict-format pages."""
        url = "https://www.webshop-a/products/milk-1l"

        associated = auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        assert len(associated) == 1
        assert "Weekly Groceries" in associated
        mock_db_manager.create_group.assert_called_once()
        mock_db_manager.add_page_to_group.assert_called_once()

    def test_no_product_groups_in_config(self, mock_db_manager):
        """Test behavior when config has no product_groups defined."""
        config_data = {"database": {"url": "./test.db"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            empty_config = f.name

        try:
            url = "https://www.webshop-a/products/test"
            associated = auto_associate_with_groups(url, mock_db_manager, empty_config)

            assert len(associated) == 0
            mock_db_manager.create_group.assert_not_called()
        finally:
            Path(empty_config).unlink()

    def test_tracked_page_not_found(self, temp_config_file, mock_db_manager):
        """Test behavior when tracked page doesn't exist in database yet."""
        mock_db_manager.get_tracked_page.return_value = None

        url = "https://www.webshop-a/products/coffee-500g"
        associated = auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        assert len(associated) == 0
        mock_db_manager.create_group.assert_called_once()
        mock_db_manager.add_page_to_group.assert_not_called()

    def test_exception_handling(self, mock_db_manager):
        """Test that exceptions are caught and logged, not raised."""
        invalid_config = "/nonexistent/config.yaml"

        url = "https://www.webshop-a/products/test"
        associated = auto_associate_with_groups(url, mock_db_manager, invalid_config)

        assert associated == []

    def test_create_group_with_description(self, temp_config_file, mock_db_manager):
        """Test that group description is passed to create_group."""
        url = "https://www.webshop-a/products/coffee-500g"

        auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        mock_db_manager.create_group.assert_called_once_with(
            name="Coffee - Douwe Egberts", description="Track coffee prices across stores"
        )

    def test_multiple_pages_same_url(self, mock_db_manager):
        """Test handling of duplicate URLs in same group."""
        config_data = {
            "database": {"url": ":memory:"},  # Required for AppConfig validation
            "product_groups": [
                {
                    "name": "Test Group",
                    "pages": [
                        "https://www.example.com/product",
                        "https://www.example.com/product",  # Duplicate
                    ],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            dup_config = f.name

        try:
            url = "https://www.example.com/product"
            associated = auto_associate_with_groups(url, mock_db_manager, dup_config)

            # Should only associate once per group
            assert len(associated) == 1
            assert "Test Group" in associated
        finally:
            Path(dup_config).unlink()

    def test_mixed_string_and_dict_pages(self, temp_config_file, mock_db_manager):
        """Test handling of mixed string and dict page formats."""
        url1 = "https://www.webshop-a/products/coffee-500g"  # String format
        url2 = "https://www.webshop-a/products/milk-1l"  # Dict format

        associated1 = auto_associate_with_groups(url1, mock_db_manager, temp_config_file)
        assert len(associated1) == 1

        mock_db_manager.reset_mock()

        associated2 = auto_associate_with_groups(url2, mock_db_manager, temp_config_file)
        assert len(associated2) == 1


class TestAutoAssociationIntegration:
    """Integration tests for automatic group association."""

    def test_idempotency(self, temp_config_file, mock_db_manager):
        """Test that running auto_associate multiple times is safe."""
        url = "https://www.webshop-a/products/coffee-500g"

        associated1 = auto_associate_with_groups(url, mock_db_manager, temp_config_file)
        mock_db_manager.reset_mock()
        associated2 = auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        assert associated1 == associated2
        assert len(associated2) == 1

    @patch("src.price_tracker.group_helpers.logger")
    def test_debug_logging(self, mock_logger, temp_config_file, mock_db_manager):
        """Test that debug logs are generated for associations."""
        url = "https://www.webshop-a/products/coffee-500g"

        auto_associate_with_groups(url, mock_db_manager, temp_config_file)

        assert mock_logger.debug.called
        debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("Found URL in group" in str(call) for call in debug_calls)

    @patch("src.price_tracker.group_helpers.logger")
    def test_error_logging(self, mock_logger, mock_db_manager):
        """Test that errors are logged with warning level."""
        url = "https://www.webshop-a/products/test"
        invalid_config = "/nonexistent/path/config.yaml"

        auto_associate_with_groups(url, mock_db_manager, invalid_config)

        mock_logger.warning.assert_called_once()
        warning_msg = str(mock_logger.warning.call_args)
        assert "Failed to auto-associate" in warning_msg
