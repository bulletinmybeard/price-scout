from unittest.mock import MagicMock, patch

from src.price_tracker.scraping_worker import scrape_single_url


class TestGroupFlag:
    """Test suite for --group flag delegation through scraping_worker."""

    def test_scrape_single_url_with_group(self, mock_tracker, mock_factory):
        """Test that --group is passed to tracker with auto-association disabled."""
        url = "https://www.store-a.example/test-product"
        group_name = "Test Group"

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        assert result[1] == url
        mock_tracker.track_product_url.assert_called_once_with(
            url,
            "store_a",
            track_to_db=True,
            group_name=group_name,
            auto_associate_groups=False,
        )

    def test_scrape_single_url_without_group(self, mock_tracker, mock_factory):
        """Test that auto-association is enabled when --group is not used."""
        url = "https://www.store-a.example/test-product"

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=None,
            )

        assert result[0] == "scraped"
        assert result[1] == url
        mock_tracker.track_product_url.assert_called_once_with(
            url,
            "store_a",
            track_to_db=True,
            group_name=None,
            auto_associate_groups=True,
        )

    def test_scrape_single_url_check_mode_ignores_group(self, mock_tracker, mock_factory):
        """Test that check mode fetches only and does not persist or associate groups."""
        url = "https://www.store-a.example/test-product"
        group_name = "Test Group"

        mock_product = MagicMock()
        mock_product.name = "Test Product"
        mock_product.current_price = 9.99
        mock_tracker.fetch_product_only.return_value = mock_product

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=True,
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        assert result[1] == url
        mock_tracker.fetch_product_only.assert_called_once_with(url, "store_a")
        mock_tracker.track_product_url.assert_not_called()

    def test_group_takes_priority_over_config(self, mock_tracker, mock_factory):
        """Test that --group disables config-based auto-association."""
        url = "https://www.store-a.example/test-product"
        group_name = "CLI Group"

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        mock_tracker.track_product_url.assert_called_once_with(
            url,
            "store_a",
            track_to_db=True,
            group_name=group_name,
            auto_associate_groups=False,
        )

    def test_group_name_with_special_characters(self, mock_tracker, mock_factory):
        """Test that group names with special characters are passed through."""
        url = "https://www.store-a.example/test-product"
        group_name = "Weekly Groceries - Store-A (2024)"

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        mock_tracker.track_product_url.assert_called_once_with(
            url,
            "store_a",
            track_to_db=True,
            group_name=group_name,
            auto_associate_groups=False,
        )


class TestGroupFlagEdgeCases:
    """Edge case tests for --group flag."""

    def test_empty_group_name(self, mock_tracker, mock_factory):
        """Test that empty group name disables explicit association."""
        url = "https://www.store-a.example/test-product"
        group_name = ""

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        mock_tracker.track_product_url.assert_called_once_with(
            url,
            "store_a",
            track_to_db=True,
            group_name=group_name,
            auto_associate_groups=False,
        )

    def test_whitespace_group_name(self, mock_tracker, mock_factory):
        """Test that whitespace-only group name is passed through."""
        url = "https://www.store-a.example/test-product"
        group_name = "   "

        with patch(
            "src.price_tracker.scraping_worker.detect_provider_from_url",
            return_value=("store_a", {}),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        mock_tracker.track_product_url.assert_called_once_with(
            url,
            "store_a",
            track_to_db=True,
            group_name=group_name,
            auto_associate_groups=False,
        )
