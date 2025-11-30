from src.providers.configurable_provider import ConfigurableProvider


class TestOfferSelection:
    """Test offer selection strategies."""

    def test_select_best_offer_first_strategy(self):
        """Test 'first' strategy selects first offer."""
        offers = [
            {"price": 509.99, "availability": "InStock"},
            {"price": 495.99, "availability": "OutOfStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="first")

        assert result == {"price": 509.99, "availability": "InStock"}

    def test_select_best_offer_cheapest_strategy(self):
        """Test 'cheapest' strategy selects lowest price regardless of availability."""
        offers = [
            {"price": 509.99, "availability": "InStock"},
            {"price": 495.99, "availability": "OutOfStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest")

        assert result == {"price": 491.99, "availability": "InStock"}
        assert result["price"] == 491.99

    def test_select_best_offer_cheapest_available_strategy(self):
        """Test 'cheapest_available' strategy selects cheapest in-stock offer."""
        offers = [
            {"price": 509.99, "availability": "InStock"},
            {"price": 495.99, "availability": "OutOfStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest_available")

        # Should select cheapest in-stock (491.99), not the out-of-stock 495.99
        assert result == {"price": 491.99, "availability": "InStock"}
        assert result["price"] == 491.99

    def test_select_best_offer_cheapest_available_when_no_stock(self):
        """Test 'cheapest_available' falls back to cheapest when nothing in stock."""
        offers = [
            {"price": 509.99, "availability": "OutOfStock"},
            {"price": 495.99, "availability": "OutOfStock"},
            {"price": 491.99, "availability": "OutOfStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest_available")

        # Should fall back to cheapest overall when nothing in stock
        assert result["price"] == 491.99

    def test_select_best_offer_with_mixed_availability_strings(self):
        """Test that different availability string formats are handled."""
        offers = [
            {"price": 509.99, "availability": "https://schema.org/InStock"},
            {"price": 495.99, "availability": "OutOfStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest_available")

        # Should select one of the in-stock items (cheapest)
        assert result["price"] in [491.99, 509.99]
        assert "InStock" in str(result["availability"])

    def test_select_best_offer_empty_list(self):
        """Test empty offer list returns empty dict."""
        offers = []

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest")

        assert result == {}

    def test_select_best_offer_unknown_strategy_fallback(self):
        """Test unknown strategy falls back to 'first'."""
        offers = [
            {"price": 509.99, "availability": "InStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="unknown_strategy")

        # Should fall back to first
        assert result == {"price": 509.99, "availability": "InStock"}

    def test_select_best_offer_with_none_prices(self):
        """Test handles offers with None prices gracefully."""
        offers = [
            {"price": None, "availability": "InStock"},
            {"price": 495.99, "availability": "InStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest")

        # Should skip None price and select cheapest valid one
        assert result["price"] == 491.99

    def test_select_best_offer_default_strategy(self):
        """Test default strategy is 'first' when not specified."""
        offers = [
            {"price": 509.99, "availability": "InStock"},
            {"price": 491.99, "availability": "InStock"},
        ]

        # Call without strategy parameter (should default to "first")
        result = ConfigurableProvider._select_best_offer(offers)

        assert result == {"price": 509.99, "availability": "InStock"}

    def test_mediamarkt_real_world_scenario(self):
        """Test MediaMarkt real-world scenario with 3 price offers.

        This matches the exact structure found in MediaMarkt's JSON-LD:
        - Offer 1: €509.99 in stock (highest)
        - Offer 2: €495.99 (no availability info)
        - Offer 3: €491.99 in stock (cheapest!)

        Expected: Select €491.99 (cheapest available)
        """
        offers = [
            {"price": 509.99, "priceCurrency": "EUR", "availability": "InStock"},
            {"price": 495.99, "priceCurrency": "EUR"},
            {"price": 491.99, "priceCurrency": "EUR", "availability": "InStock"},
        ]

        result = ConfigurableProvider._select_best_offer(offers, strategy="cheapest_available")

        assert result["price"] == 491.99
        assert result["priceCurrency"] == "EUR"
        assert result["availability"] == "InStock"
