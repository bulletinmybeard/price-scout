import pytest

from src.providers.transformations import Transformations


class TestParsePriceBasic:
    """Test basic parse_price functionality."""

    def test_parse_float_passthrough(self):
        """Float values should pass through unchanged."""
        result = Transformations.parse_price(19.99)
        assert result == 19.99

    def test_parse_int_passthrough(self):
        """Integer values should be converted to float."""
        result = Transformations.parse_price(20)
        assert result == 20.0

    def test_parse_none(self):
        """None should return None."""
        result = Transformations.parse_price(None)
        assert result is None

    def test_parse_empty_string(self):
        """Empty string should return None."""
        result = Transformations.parse_price("")
        assert result is None

    def test_parse_whitespace(self):
        """Whitespace-only string should return None."""
        result = Transformations.parse_price("   ")
        assert result is None


class TestParsePriceSimpleFormats:
    """Test parsing simple price formats without config."""

    def test_parse_european_decimal(self):
        """European format with comma decimal separator."""
        result = Transformations.parse_price("2,99")
        assert result == 2.99

    def test_parse_us_decimal(self):
        """US format with dot decimal separator."""
        result = Transformations.parse_price("2.99")
        assert result == 2.99

    def test_parse_european_with_thousand_separator(self):
        """European format: 1.234,56."""
        result = Transformations.parse_price("1.234,56")
        assert result == 1234.56

    def test_parse_us_with_thousand_separator(self):
        """US format: 1,234.56."""
        result = Transformations.parse_price("1,234.56")
        assert result == 1234.56

    def test_parse_no_decimals(self):
        """Integer price without decimals."""
        result = Transformations.parse_price("15")
        assert result == 15.0


class TestParsePriceRemovePrefixes:
    """Test prefix removal via config."""

    def test_remove_single_prefix(self):
        """Remove Dutch prefix."""
        config = {"remove_prefixes": ["prijs:"]}
        result = Transformations.parse_price("prijs: 2,99", config)
        assert result == 2.99

    def test_remove_multiple_prefixes(self):
        """Config with multiple prefixes - matches first."""
        config = {"remove_prefixes": ["nieuwe prijs:", "oude prijs:", "prijs:"]}
        result = Transformations.parse_price("nieuwe prijs: 4,99", config)
        assert result == 4.99

    def test_case_insensitive_prefix(self):
        """Prefix removal should be case-insensitive."""
        config = {"remove_prefixes": ["price:"]}
        result = Transformations.parse_price("PRICE: 9.99", config)
        assert result == 9.99

    def test_prefix_with_extra_whitespace(self):
        """Handle extra whitespace after prefix."""
        config = {"remove_prefixes": ["price:"]}
        result = Transformations.parse_price("price:   19.99", config)
        assert result == 19.99

    def test_no_prefix_match(self):
        """Price without matching prefix should still parse."""
        config = {"remove_prefixes": ["price:"]}
        result = Transformations.parse_price("€9.99", config)
        assert result == 9.99


class TestParsePriceRemoveSymbols:
    """Test currency symbol removal via config."""

    def test_remove_euro_symbol(self):
        """Remove € symbol."""
        config = {"remove_symbols": ["€"]}
        result = Transformations.parse_price("€2,99", config)
        assert result == 2.99

    def test_remove_multiple_symbols(self):
        """Remove multiple currency symbols."""
        config = {"remove_symbols": ["€", "EUR", "$"]}
        result = Transformations.parse_price("€ 4,99 EUR", config)
        assert result == 4.99

    def test_symbol_in_middle(self):
        """Symbol in middle of price."""
        config = {"remove_symbols": ["€"]}
        result = Transformations.parse_price("2€99", config)
        # This becomes "299" after symbol removal
        assert result == 299.0


class TestParsePriceFormatRules:
    """Test custom format rules via regex."""

    def test_space_separated_decimal_store_d(self):
        """Store-D format: '1. 99' -> '1.99'."""
        config = {"format_rules": [{"pattern": r"^(\d+)\.\s+(\d{2})$", "replacement": r"\1.\2"}]}
        result = Transformations.parse_price("1. 99", config)
        assert result == 1.99

    def test_space_separated_two_digit_euros(self):
        """Store-D format with two-digit euros: '12. 50' -> '12.50'."""
        config = {"format_rules": [{"pattern": r"^(\d+)\.\s+(\d{2})$", "replacement": r"\1.\2"}]}
        result = Transformations.parse_price("12. 50", config)
        assert result == 12.50

    def test_price_range_take_first(self):
        """Price range '2.29 - 3.69' -> take first price."""
        config = {"format_rules": [{"pattern": r"^([\d.,]+)\s*-\s*[\d.,]+$", "replacement": r"\1"}]}
        result = Transformations.parse_price("2.29 - 3.69", config)
        assert result == 2.29

    def test_multiple_format_rules(self):
        """Apply multiple format rules in sequence."""
        config = {
            "format_rules": [
                # First rule: handle range
                {"pattern": r"^([\d.,]+)\s*-\s*[\d.,]+$", "replacement": r"\1"},
                # Second rule: remove suffix
                {"pattern": r"(\d+,\d+)\s*per\s*stuk", "replacement": r"\1"},
            ]
        }
        result = Transformations.parse_price("2,99 per stuk", config)
        assert result == 2.99


class TestParsePriceDecimalFormat:
    """Test explicit decimal format specification."""

    def test_explicit_european_format(self):
        """Force European format interpretation."""
        config = {"decimal_format": "eu"}
        result = Transformations.parse_price("1.234,56", config)
        assert result == 1234.56

    def test_explicit_us_format(self):
        """Force US format interpretation."""
        config = {"decimal_format": "us"}
        result = Transformations.parse_price("1,234.56", config)
        assert result == 1234.56

    def test_auto_format_european(self):
        """Auto-detect European format."""
        config = {"decimal_format": "auto"}
        result = Transformations.parse_price("2,99", config)
        assert result == 2.99

    def test_auto_format_us(self):
        """Auto-detect US format."""
        config = {"decimal_format": "auto"}
        result = Transformations.parse_price("2.99", config)
        assert result == 2.99

    def test_auto_format_with_both_separators_european(self):
        """Auto-detect European when both comma and dot present."""
        config = {"decimal_format": "auto"}
        # Last separator (comma) is decimal
        result = Transformations.parse_price("1.234,56", config)
        assert result == 1234.56

    def test_auto_format_with_both_separators_us(self):
        """Auto-detect US when both comma and dot present."""
        config = {"decimal_format": "auto"}
        # Last separator (dot) is decimal
        result = Transformations.parse_price("1,234.56", config)
        assert result == 1234.56


class TestParsePriceFullConfig:
    """Test complete config with all features (Store-D-style)."""

    @pytest.fixture
    def store_d_config(self):
        """Store-D price cleaning configuration."""
        return {
            "remove_prefixes": ["nieuwe prijs:", "oude prijs:", "prijs:"],
            "remove_symbols": ["€", "EUR"],
            "format_rules": [
                # Handle "1. 99" format
                {"pattern": r"^(\d+)\.\s+(\d{2})$", "replacement": r"\1.\2"},
                # Handle price ranges
                {"pattern": r"^([\d.,]+)\s*-\s*[\d.,]+$", "replacement": r"\1"},
            ],
            "decimal_format": "eu",
        }

    def test_store_d_simple_price(self, store_d_config):
        """Simple Store-D price."""
        result = Transformations.parse_price("€ 2,99", store_d_config)
        assert result == 2.99

    def test_store_d_space_separated(self, store_d_config):
        """Store-D's special '1. 99' format."""
        result = Transformations.parse_price("€ 1. 99", store_d_config)
        assert result == 1.99

    def test_store_d_with_prefix(self, store_d_config):
        """Store-D price with Dutch prefix."""
        result = Transformations.parse_price("nieuwe prijs: € 4,99", store_d_config)
        assert result == 4.99

    def test_store_d_promotion_price(self, store_d_config):
        """Store-D promotion with all features."""
        result = Transformations.parse_price("nieuwe prijs: € 12. 50", store_d_config)
        assert result == 12.50

    def test_store_d_price_range(self, store_d_config):
        """Store-D price range - take first."""
        result = Transformations.parse_price("€ 2,29 - 3,69", store_d_config)
        assert result == 2.29


class TestParsePriceEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_price_string(self):
        """Invalid price string should return None."""
        result = Transformations.parse_price("not a price")
        assert result is None

    def test_partial_number(self):
        """Partial number after cleaning should fail gracefully."""
        config = {"remove_symbols": ["€", "."]}
        # This removes both € and dots, leaving "299" which is valid
        result = Transformations.parse_price("€2.99", config)
        assert result == 299.0  # Becomes "299" after symbol removal

    def test_only_symbols(self):
        """String with only symbols should return None."""
        result = Transformations.parse_price("€$£")
        assert result is None

    def test_empty_config(self):
        """Empty config should still parse basic prices."""
        config = {}
        result = Transformations.parse_price("2.99", config)
        assert result == 2.99

    def test_malformed_format_rule(self):
        """Malformed format rule should be skipped."""
        config = {
            "format_rules": [
                {"pattern": r"\d+"},  # Missing 'replacement'
            ]
        }
        result = Transformations.parse_price("2.99", config)
        assert result == 2.99

    def test_very_large_price(self):
        """Very large price should parse correctly."""
        result = Transformations.parse_price("9.999.999,99")
        assert result == 9999999.99


class TestApplyTransformation:
    """Test parse_price via apply_transformation dispatcher."""

    def test_apply_parse_price_transformation(self):
        """Test parse_price through apply_transformation."""
        transformation = {
            "type": "parse_price",
            "remove_symbols": ["€"],
            "decimal_format": "eu",
        }
        result = Transformations.apply_transformation("€2,99", transformation)
        assert result == 2.99

    def test_apply_store_d_transformation(self):
        """Full Store-D transformation via apply_transformation."""
        transformation = {
            "type": "parse_price",
            "remove_prefixes": ["prijs:"],
            "remove_symbols": ["€"],
            "format_rules": [{"pattern": r"^(\d+)\.\s+(\d{2})$", "replacement": r"\1.\2"}],
            "decimal_format": "eu",
        }
        result = Transformations.apply_transformation("prijs: € 1. 99", transformation)
        assert result == 1.99

    def test_apply_transformation_without_config(self):
        """Parse price transformation with only type specified."""
        transformation = {"type": "parse_price"}
        result = Transformations.apply_transformation("2.99", transformation)
        assert result == 2.99
