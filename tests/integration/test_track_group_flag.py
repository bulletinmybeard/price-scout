from unittest.mock import MagicMock, patch

from src.price_tracker.scraping_worker import scrape_single_url


class TestGroupFlag:
    """Test suite for --group flag functionality."""

    def test_scrape_single_url_with_group(self, mock_tracker, mock_factory, mock_db_manager):
        """Test that group is created and associated when --group flag is used."""
        url = "https://www.store-a.example/test-product"
        group_name = "Test Group"

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
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

        mock_db_manager.create_group.assert_called_once_with(name=group_name)

        mock_db_manager.add_page_to_group.assert_called_once_with(page_id=1, group_id=1)

    def test_scrape_single_url_without_group(self, mock_tracker, mock_factory, mock_db_manager):
        """Test that no group is created when --group flag is not used."""
        url = "https://www.store-a.example/test-product"

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
            patch("src.price_tracker.scraping_worker.auto_associate_with_groups", return_value=[]),
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

        assert mock_db_manager.add_page_to_group.call_count == 0, (
            "Should not associate when no group specified"
        )

    def test_scrape_single_url_group_creation_failure(
        self, mock_tracker, mock_factory, mock_db_manager
    ):
        """Test that group creation failure doesn't break tracking."""
        url = "https://www.store-a.example/test-product"
        group_name = "Test Group"

        mock_db_manager.create_group.side_effect = Exception("Database error")

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
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

        mock_db_manager.add_page_to_group.assert_not_called()

    def test_scrape_single_url_check_mode_ignores_group(
        self, mock_tracker, mock_factory, mock_db_manager
    ):
        url = "https://www.store-a.example/test-product"
        group_name = "Test Group"

        mock_product = MagicMock()
        mock_product.name = "Test Product"
        mock_tracker.fetch_product_only.return_value = mock_product

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=True,  # Check mode
                db_url=":memory:",
                group_name=group_name,
            )

        assert result[0] == "scraped"
        assert result[1] == url

        mock_db_manager.create_group.assert_not_called()
        mock_db_manager.add_page_to_group.assert_not_called()

    def test_group_takes_priority_over_config(self, mock_tracker, mock_factory, mock_db_manager):
        """Test that --group flag takes priority over config.yaml auto-association."""
        url = "https://www.store-a.example/test-product"
        group_name = "CLI Group"

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
            patch(
                "src.price_tracker.scraping_worker.auto_associate_with_groups",
                return_value=["Config Group"],
            ) as mock_auto_associate,
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

        mock_db_manager.create_group.assert_called_once_with(name="CLI Group")

        mock_auto_associate.assert_not_called()

    def test_group_name_with_special_characters(self, mock_tracker, mock_factory, mock_db_manager):
        """Test that group names with special characters work correctly."""
        url = "https://www.store-a.example/test-product"
        group_name = "Weekly Groceries - Store-A (2024)"

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
        ):
            result = scrape_single_url(
                url=url,
                tracker=mock_tracker,
                factory=mock_factory,
                check=False,
                db_url=":memory:",
                group_name=group_name,
            )

        mock_db_manager.create_group.assert_called_once_with(name=group_name)

        assert result[0] == "scraped"

    def test_group_association_when_page_not_found(
        self, mock_tracker, mock_factory, mock_db_manager
    ):
        """Test group association handles missing tracked page gracefully."""
        url = "https://www.store-a.example/test-product"
        group_name = "Test Group"

        mock_db_manager.get_tracked_page.return_value = None

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
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

        mock_db_manager.create_group.assert_called_once()

        mock_db_manager.add_page_to_group.assert_not_called()


class TestGroupFlagEdgeCases:
    """Edge case tests for --group flag."""

    def test_empty_group_name(self, mock_tracker, mock_factory, mock_db_manager):
        """Test that empty group name is handled gracefully."""
        url = "https://www.store-a.example/test-product"
        group_name = ""

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
            patch("src.price_tracker.scraping_worker.auto_associate_with_groups", return_value=[]),
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

        mock_db_manager.create_group.assert_not_called()

    def test_whitespace_group_name(self, mock_tracker, mock_factory, mock_db_manager):
        """Test that whitespace-only group name is treated as valid."""
        url = "https://www.store-a.example/test-product"
        group_name = "   "

        with (
            patch(
                "src.price_tracker.scraping_worker.detect_provider_from_url",
                return_value=("store_a", {}),
            ),
            patch(
                "src.price_tracker.scraping_worker.DatabaseManager", return_value=mock_db_manager
            ),
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

        mock_db_manager.create_group.assert_called_once_with(name=group_name)
