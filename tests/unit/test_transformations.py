from src.providers.transformations import Transformations


class TestRegexReplace:
    """Tests for regex_replace transformation."""

    def test_regex_replace_single_pattern(self):
        """Test replacing with single pattern."""
        value = "Product Name | Store"
        result = Transformations.regex_replace(value, [" \\| Store"])
        assert result == "Product Name"

    def test_regex_replace_multiple_patterns(self):
        """Test replacing with multiple patterns."""
        value = "Buy Product Name | Store Online"
        result = Transformations.regex_replace(value, ["Buy ", " Online", " \\| Store"])
        assert result == "Product Name"

    def test_regex_replace_no_match(self):
        """Test regex replace when pattern doesn't match."""
        value = "Product Name"
        result = Transformations.regex_replace(value, ["NonExistent"])
        assert result == "Product Name"

    def test_regex_replace_empty_patterns(self):
        """Test regex replace with empty patterns list."""
        value = "Product Name"
        result = Transformations.regex_replace(value, [])
        assert result == "Product Name"

    def test_regex_replace_empty_value(self):
        """Test regex replace with empty value."""
        value = ""
        result = Transformations.regex_replace(value, ["test"])
        assert result == ""

    def test_regex_replace_case_insensitive(self):
        """Test regex replace is case insensitive by default."""
        value = "Product NAME | STORE"
        result = Transformations.regex_replace(value, [" \\| store"])
        assert result == "Product NAME"


class TestSplitString:
    """Tests for split_string transformation."""

    def test_split_comma_separated(self):
        """Test splitting comma-separated values."""
        value = "Category1, Category2, Category3"
        result = Transformations.split_string(value, ",")
        assert result == ["Category1", "Category2", "Category3"]

    def test_split_pipe_separated(self):
        """Test splitting pipe-separated values."""
        value = "Tag1|Tag2|Tag3"
        result = Transformations.split_string(value, "|")
        assert result == ["Tag1", "Tag2", "Tag3"]

    def test_split_trims_whitespace(self):
        """Test that split transformation trims whitespace from items."""
        value = "Item1 , Item2 , Item3"
        result = Transformations.split_string(value, ",", strip=True)
        assert result == ["Item1", "Item2", "Item3"]

    def test_split_single_value(self):
        """Test splitting string with no delimiter."""
        value = "SingleValue"
        result = Transformations.split_string(value, ",")
        assert result == ["SingleValue"]

    def test_split_empty_string(self):
        """Test splitting empty string."""
        value = ""
        result = Transformations.split_string(value, ",")
        assert result == []

    def test_split_already_list(self):
        """Test splitting value that's already a list."""
        value = ["Item1", "Item2"]
        result = Transformations.split_string(value, ",")
        assert result == ["Item1", "Item2"]

    def test_split_removes_empty_strings(self):
        """Test that empty strings are removed after split."""
        value = "Item1,,Item2"
        result = Transformations.split_string(value, ",")
        assert result == ["Item1", "Item2"]


class TestParsePriceSpecification:
    """Tests for parse_price_specification transformation."""

    def test_parse_price_specification_basic(self):
        """Test basic price specification extraction."""
        value = {"price": "9.99", "unitCode": "KG"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result == "€9.99/kg"

    def test_parse_price_specification_different_units(self):
        """Test price specification with different unit codes."""
        assert (
            Transformations.parse_price_specification({"price": "5.99", "unitCode": "KGM"}, "EUR")
            == "€5.99/kg"
        )

        assert (
            Transformations.parse_price_specification({"price": "2.50", "unitCode": "LTR"}, "EUR")
            == "€2.50/l"
        )

        assert (
            Transformations.parse_price_specification({"price": "0.99", "unitCode": "GRM"}, "EUR")
            == "€0.99/g"
        )

        assert (
            Transformations.parse_price_specification({"price": "3.25", "unitCode": "MLT"}, "EUR")
            == "€3.25/ml"
        )

    def test_parse_price_specification_different_currencies(self):
        """Test price specification with different currencies."""
        value = {"price": "10.00", "unitCode": "KG"}

        result_eur = Transformations.parse_price_specification(value, "EUR")
        assert result_eur == "€10.00/kg"

        result_usd = Transformations.parse_price_specification(value, "USD")
        assert result_usd == "$10.00/kg"

        result_gbp = Transformations.parse_price_specification(value, "GBP")
        assert result_gbp == "£10.00/kg"

    def test_parse_price_specification_missing_price(self):
        """Test price specification with missing price returns None."""
        value = {"unitCode": "KG"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result is None

    def test_parse_price_specification_missing_unit(self):
        """Test price specification with missing unit code returns None."""
        value = {"price": "9.99"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result is None

    def test_parse_price_specification_invalid_price(self):
        """Test price specification with invalid price returns None."""
        value = {"price": "not_a_number", "unitCode": "KG"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result is None

    def test_parse_price_specification_numeric_price(self):
        """Test price specification with numeric (not string) price."""
        value = {"price": 12.50, "unitCode": "L"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result == "€12.50/l"


class TestParseSchemaAvailability:
    """Tests for parse_schema_availability transformation."""

    def test_parse_schema_availability_in_stock(self):
        """Test parsing InStock URL."""
        url = "https://schema.org/InStock"
        result = Transformations.parse_schema_availability(url)
        assert result is True

    def test_parse_schema_availability_out_of_stock(self):
        """Test parsing OutOfStock URL."""
        url = "https://schema.org/OutOfStock"
        result = Transformations.parse_schema_availability(url)
        assert result is False

    def test_parse_schema_availability_pre_order(self):
        """Test parsing PreOrder URL."""
        url = "https://schema.org/PreOrder"
        result = Transformations.parse_schema_availability(url)
        assert result is False

    def test_parse_schema_availability_case_insensitive(self):
        """Test that URL parsing is case insensitive."""
        url = "https://SCHEMA.ORG/INSTOCK"
        result = Transformations.parse_schema_availability(url)
        assert result is True

    def test_parse_schema_availability_with_underscore(self):
        """Test parsing with underscore variant."""
        url = "https://schema.org/in_stock"
        result = Transformations.parse_schema_availability(url)
        assert result is True

    def test_parse_schema_availability_available_keyword(self):
        """Test parsing with 'available' keyword."""
        url = "https://example.com/available"
        result = Transformations.parse_schema_availability(url)
        assert result is True

    def test_parse_schema_availability_empty_string(self):
        """Test parsing empty string returns False."""
        result = Transformations.parse_schema_availability("")
        assert result is False

    def test_parse_schema_availability_none(self):
        """Test parsing None returns False."""
        result = Transformations.parse_schema_availability(None)
        assert result is False


class TestApplyTransformation:
    """Tests for apply_transformation dispatcher."""

    def test_apply_regex_replace_transformation(self):
        """Test applying regex_replace transformation."""
        value = "Product Name | Store"
        transform = {"type": "regex_replace", "patterns": [" \\| Store"]}
        result = Transformations.apply_transformation(value, transform)
        assert result == "Product Name"

    def test_apply_split_transformation(self):
        """Test applying split transformation."""
        value = "Item1, Item2, Item3"
        transform = {"type": "split", "delimiter": ","}
        result = Transformations.apply_transformation(value, transform)
        assert result == ["Item1", "Item2", "Item3"]

    def test_apply_price_specification_transformation(self):
        """Test applying price_specification transformation."""
        value = {"price": "9.99", "unitCode": "KG"}
        transform = {"type": "price_specification", "currency": "EUR"}
        result = Transformations.apply_transformation(value, transform)
        assert result == "€9.99/kg"

    def test_apply_schema_availability_transformation(self):
        """Test applying schema_availability transformation."""
        value = "https://schema.org/InStock"
        transform = {"type": "schema_availability"}
        result = Transformations.apply_transformation(value, transform)
        assert result is True

    def test_apply_unknown_transformation_returns_unchanged(self):
        """Test that unknown transformation type returns value unchanged."""
        value = "test_value"
        transform = {"type": "unknown_type"}
        result = Transformations.apply_transformation(value, transform)
        assert result == "test_value"

    def test_apply_transformation_with_empty_dict(self):
        """Test transformation with empty dict."""
        value = "test_value"
        transform = {}
        result = Transformations.apply_transformation(value, transform)
        assert result == "test_value"

    def test_apply_transformation_with_none(self):
        """Test transformation with None."""
        value = "test_value"
        result = Transformations.apply_transformation(value, None)
        assert result == "test_value"

    def test_apply_transformation_with_non_dict(self):
        """Test transformation with non-dict value."""
        value = "test_value"
        result = Transformations.apply_transformation(value, "not_a_dict")
        assert result == "test_value"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_regex_replace_with_special_characters(self):
        """Test regex replace with special regex characters."""
        value = "Price: $10.99"
        result = Transformations.regex_replace(value, ["Price: \\$"])
        assert result == "10.99"

    def test_split_with_multiple_consecutive_delimiters(self):
        """Test split with multiple consecutive delimiters."""
        value = "Item1,,,Item2"
        result = Transformations.split_string(value, ",")
        assert result == ["Item1", "Item2"]

    def test_price_specification_with_zero_price(self):
        """Test price specification with zero price."""
        value = {"price": "0.00", "unitCode": "KG"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result == "€0.00/kg"

    def test_price_specification_with_large_price(self):
        """Test price specification with large price."""
        value = {"price": "999.99", "unitCode": "KG"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result == "€999.99/kg"

    def test_unknown_unit_code_preserved(self):
        """Test that unknown unit codes are preserved in lowercase."""
        value = {"price": "5.00", "unitCode": "UNKNOWN"}
        result = Transformations.parse_price_specification(value, "EUR")
        assert result == "€5.00/unknown"

    def test_unknown_currency_uses_code(self):
        """Test that unknown currency uses currency code."""
        value = {"price": "5.00", "unitCode": "KG"}
        result = Transformations.parse_price_specification(value, "JPY")
        assert result == "¥5.00/kg"  # JPY now has symbol in currency_symbols
