from unittest.mock import AsyncMock, MagicMock

import pytest

from src.providers.selector_extractor import SelectorConfig, SelectorExtractor


class TestSelectorConfig:
    """Test SelectorConfig initialization and validation."""

    def test_init_default_css_selector(self):
        """Test creating a basic CSS selector config."""
        config = SelectorConfig(selector="h1.product-title")

        assert config.selector == "h1.product-title"
        assert config.selector_type == "css"
        assert config.attribute is None
        assert config.check_exists is False
        assert config.check_not_disabled is False
        assert config.multiple is False

    def test_init_xpath_selector(self):
        """Test creating an XPath selector config."""
        config = SelectorConfig(selector="//h1[@class='title']", selector_type="xpath")

        assert config.selector == "//h1[@class='title']"
        assert config.selector_type == "xpath"

    def test_init_with_attribute(self):
        """Test creating selector config with attribute extraction."""
        config = SelectorConfig(selector="img.product", attribute="src")

        assert config.selector == "img.product"
        assert config.attribute == "src"

    def test_init_with_boolean_checks(self):
        """Test creating selector config for boolean field."""
        config = SelectorConfig(
            selector="button.add-to-cart", check_exists=True, check_not_disabled=True
        )

        assert config.check_exists is True
        assert config.check_not_disabled is True

    def test_init_with_multiple(self):
        """Test creating selector config for multiple elements."""
        config = SelectorConfig(selector="img.gallery", attribute="src", multiple=True)

        assert config.multiple is True

    def test_invalid_selector_type(self):
        """Test that invalid selector type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid selector_type"):
            SelectorConfig(selector="test", selector_type="invalid")

    def test_repr(self):
        """Test string representation for debugging."""
        config = SelectorConfig(selector="h1", selector_type="css", attribute="data-name")
        repr_str = repr(config)

        assert "type=css" in repr_str
        assert "selector='h1'" in repr_str
        assert "attribute='data-name'" in repr_str


class TestSelectorExtractorParsing:
    """Test parsing selector configurations from YAML/dict format."""

    def test_parse_selector_config_string(self):
        """Test parsing simple string selector (CSS default)."""
        config = SelectorExtractor.parse_selector_config("h1.product-title")

        assert isinstance(config, SelectorConfig)
        assert config.selector == "h1.product-title"
        assert config.selector_type == "css"

    def test_parse_selector_config_dict_minimal(self):
        """Test parsing dict with minimal config."""
        config = SelectorExtractor.parse_selector_config({"selector": ".price"})

        assert config.selector == ".price"
        assert config.selector_type == "css"

    def test_parse_selector_config_dict_full(self):
        """Test parsing dict with full config."""
        config = SelectorExtractor.parse_selector_config(
            {
                "selector": "//h1",
                "type": "xpath",
                "attribute": "data-name",
                "check_exists": True,
                "multiple": True,
            }
        )

        assert config.selector == "//h1"
        assert config.selector_type == "xpath"
        assert config.attribute == "data-name"
        assert config.check_exists is True
        assert config.multiple is True

    def test_parse_selector_config_missing_selector(self):
        """Test that missing selector raises ValueError."""
        with pytest.raises(ValueError, match="must have 'selector' field"):
            SelectorExtractor.parse_selector_config({"type": "css"})

    def test_parse_field_selectors(self):
        """Test parsing full field selectors from extraction config."""
        extraction_config = {
            "css_selectors": {
                "name": ["h1.title", ".product-name"],
                "price": [{"selector": ".price", "type": "css"}],
                "image": [{"selector": "img", "attribute": "src"}],
            }
        }

        field_selectors = SelectorExtractor.parse_field_selectors(extraction_config)

        assert "name" in field_selectors
        assert len(field_selectors["name"]) == 2
        assert field_selectors["name"][0].selector == "h1.title"
        assert field_selectors["name"][1].selector == ".product-name"

        assert "price" in field_selectors
        assert len(field_selectors["price"]) == 1

        assert "image" in field_selectors
        assert field_selectors["image"][0].attribute == "src"

    def test_parse_field_selectors_empty(self):
        """Test parsing when no css_selectors defined."""
        field_selectors = SelectorExtractor.parse_field_selectors({})

        assert field_selectors == {}


class TestSelectorExtractorExtraction:
    """Test actual data extraction from mock Playwright pages."""

    @pytest.fixture
    def extractor(self):
        """Create SelectorExtractor instance."""
        return SelectorExtractor()

    @pytest.fixture
    def mock_page(self):
        """Create mock Playwright Page."""
        return MagicMock()

    @pytest.fixture
    def mock_element(self):
        """Create mock element with async methods."""
        element = MagicMock()
        element.text_content = AsyncMock(return_value="Product Title")
        element.get_attribute = AsyncMock(return_value=None)
        return element

    @pytest.mark.asyncio
    async def test_extract_text_content_css(self, extractor, mock_page, mock_element):
        """Test extracting text content using CSS selector."""
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="h1.title")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "Product Title"
        mock_page.query_selector.assert_called_once_with("h1.title")

    @pytest.mark.asyncio
    async def test_extract_text_content_xpath(self, extractor, mock_page, mock_element):
        """Test extracting text content using XPath selector."""
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element])

        config = SelectorConfig(selector="//h1[@class='title']", selector_type="xpath")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "Product Title"
        mock_page.query_selector_all.assert_called_once_with("xpath=//h1[@class='title']")

    @pytest.mark.asyncio
    async def test_extract_attribute(self, extractor, mock_page):
        """Test extracting element attribute."""
        mock_img = MagicMock()
        mock_img.get_attribute = AsyncMock(return_value="https://example.com/image.jpg")
        mock_page.query_selector = AsyncMock(return_value=mock_img)

        config = SelectorConfig(selector="img.product", attribute="src")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "https://example.com/image.jpg"
        mock_img.get_attribute.assert_called_once_with("src")

    @pytest.mark.asyncio
    async def test_extract_boolean_exists(self, extractor, mock_page, mock_element):
        """Test boolean extraction (element exists)."""
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="button.add-to-cart", check_exists=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is True

    @pytest.mark.asyncio
    async def test_extract_boolean_not_exists(self, extractor, mock_page):
        """Test boolean extraction (element does not exist)."""
        mock_page.query_selector = AsyncMock(return_value=None)

        config = SelectorConfig(selector="button.add-to-cart", check_exists=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_boolean_not_disabled(self, extractor, mock_page):
        """Test boolean extraction with disabled check."""
        mock_button = MagicMock()
        mock_button.get_attribute = AsyncMock(return_value=None)  # Not disabled
        mock_page.query_selector = AsyncMock(return_value=mock_button)

        config = SelectorConfig(
            selector="button.add-to-cart", check_exists=True, check_not_disabled=True
        )
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is True
        mock_button.get_attribute.assert_called_once_with("disabled")

    @pytest.mark.asyncio
    async def test_extract_boolean_is_disabled(self, extractor, mock_page):
        """Test boolean extraction when element is disabled."""
        mock_button = MagicMock()
        mock_button.get_attribute = AsyncMock(return_value="disabled")  # Disabled
        mock_page.query_selector = AsyncMock(return_value=mock_button)

        config = SelectorConfig(
            selector="button.add-to-cart", check_exists=True, check_not_disabled=True
        )
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is False

    @pytest.mark.asyncio
    async def test_extract_multiple_elements(self, extractor, mock_page):
        """Test extracting from multiple elements (array)."""
        mock_img1 = MagicMock()
        mock_img1.get_attribute = AsyncMock(return_value="https://example.com/img1.jpg")
        mock_img2 = MagicMock()
        mock_img2.get_attribute = AsyncMock(return_value="https://example.com/img2.jpg")

        mock_page.query_selector_all = AsyncMock(return_value=[mock_img1, mock_img2])

        config = SelectorConfig(selector="img.gallery", attribute="src", multiple=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]

    @pytest.mark.asyncio
    async def test_extract_field_with_fallback_success_first(
        self, extractor, mock_page, mock_element
    ):
        """Test extract_field tries first selector successfully."""
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        configs = [
            SelectorConfig(selector="h1.title"),
            SelectorConfig(selector=".product-name"),
        ]

        result = await extractor.extract_field(mock_page, "name", configs)

        assert result == "Product Title"
        mock_page.query_selector.assert_called_once_with("h1.title")

    @pytest.mark.asyncio
    async def test_extract_field_with_fallback_second_succeeds(
        self, extractor, mock_page, mock_element
    ):
        """Test extract_field falls back to second selector."""
        mock_page.query_selector = AsyncMock(side_effect=[None, mock_element])

        configs = [
            SelectorConfig(selector="h1.title"),
            SelectorConfig(selector=".product-name"),
        ]

        result = await extractor.extract_field(mock_page, "name", configs)

        assert result == "Product Title"
        assert mock_page.query_selector.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_field_all_fail(self, extractor, mock_page):
        """Test extract_field when all selectors fail."""
        mock_page.query_selector = AsyncMock(return_value=None)

        configs = [
            SelectorConfig(selector="h1.title"),
            SelectorConfig(selector=".product-name"),
        ]

        result = await extractor.extract_field(mock_page, "name", configs)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_all_fields(self, extractor, mock_page):
        """Test extracting multiple fields at once."""
        # Mock different elements for different selectors
        mock_title = MagicMock()
        mock_title.text_content = AsyncMock(return_value="Product Title")

        mock_price = MagicMock()
        mock_price.text_content = AsyncMock(return_value="€19.99")

        async def query_selector_side_effect(selector):
            if "h1" in selector:
                return mock_title
            elif "price" in selector:
                return mock_price
            return None

        mock_page.query_selector = AsyncMock(side_effect=query_selector_side_effect)

        field_selectors = {
            "name": [SelectorConfig(selector="h1.title")],
            "price": [SelectorConfig(selector=".price")],
            "missing": [SelectorConfig(selector=".does-not-exist")],
        }

        results = await extractor.extract_all_fields(mock_page, field_selectors)

        assert "name" in results
        assert results["name"] == "Product Title"
        assert "price" in results
        assert results["price"] == "€19.99"
        assert "missing" not in results  # Failed extractions not included

    @pytest.mark.asyncio
    async def test_extract_strips_whitespace(self, extractor, mock_page):
        """Test that extracted text is stripped of whitespace."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="  Product Title  \n")
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="h1")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "Product Title"

    @pytest.mark.asyncio
    async def test_extract_attribute_strips_whitespace(self, extractor, mock_page):
        """Test that extracted attributes are stripped."""
        mock_element = MagicMock()
        mock_element.get_attribute = AsyncMock(return_value="  value  ")
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="div", attribute="data-value")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "value"


class TestSelectorExtractorEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def extractor(self):
        """Create SelectorExtractor instance."""
        return SelectorExtractor()

    @pytest.fixture
    def mock_page(self):
        """Create mock Playwright Page."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_extract_field_empty_selectors(self, extractor, mock_page):
        """Test extract_field with empty selector list."""
        result = await extractor.extract_field(mock_page, "name", [])

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_field_exception_continues_to_next(self, extractor, mock_page):
        """Test that exception in one selector continues to next."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="Success")

        mock_page.query_selector = AsyncMock(side_effect=[Exception("Failed"), mock_element])

        configs = [
            SelectorConfig(selector="bad-selector"),
            SelectorConfig(selector="good-selector"),
        ]

        result = await extractor.extract_field(mock_page, "name", configs)

        assert result == "Success"

    @pytest.mark.asyncio
    async def test_find_element_invalid_type(self, extractor, mock_page):
        """Test that invalid selector type raises ValueError."""
        config = SelectorConfig(selector="test", selector_type="css")
        config.selector_type = "invalid"  # Force invalid type

        with pytest.raises(ValueError, match="Unknown selector type"):
            await extractor._find_element(mock_page, config)

    @pytest.mark.asyncio
    async def test_extract_multiple_empty_results(self, extractor, mock_page):
        """Test multiple extraction with no elements found."""
        mock_page.query_selector_all = AsyncMock(return_value=[])

        config = SelectorConfig(selector="img", multiple=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_text_content_empty_string(self, extractor, mock_page):
        """Test extraction when element returns empty string."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="")
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="div")
        result = await extractor._extract_with_selector(mock_page, config)

        # Empty string after strip should return None
        assert result is None


class TestAdvancedFeatures:
    """Test advanced selector features (Phase 2)."""

    @pytest.fixture
    def extractor(self):
        """Create SelectorExtractor instance."""
        return SelectorExtractor()

    @pytest.fixture
    def mock_page(self):
        """Create mock Playwright Page."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_wait_for_element_success(self, extractor, mock_page):
        """Test waiting for element before extraction."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="Loaded Content")

        mock_page.wait_for_selector = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector=".lazy-content", wait_for=True, wait_timeout=3000)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "Loaded Content"
        mock_page.wait_for_selector.assert_called_once_with(".lazy-content", timeout=3000)

    @pytest.mark.asyncio
    async def test_wait_for_element_timeout(self, extractor, mock_page):
        """Test wait timeout returns None."""
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))

        config = SelectorConfig(selector=".never-loads", wait_for=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is None

    @pytest.mark.asyncio
    async def test_wait_for_xpath_selector(self, extractor, mock_page):
        """Test waiting for XPath selector."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="XPath Content")

        mock_page.wait_for_selector = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element])

        config = SelectorConfig(
            selector="//div[@class='lazy']", selector_type="xpath", wait_for=True
        )
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "XPath Content"
        mock_page.wait_for_selector.assert_called_once_with(
            "xpath=//div[@class='lazy']", timeout=5000
        )

    @pytest.mark.asyncio
    async def test_visibility_check_visible(self, extractor, mock_page):
        """Test visibility check when element is visible."""
        mock_element = MagicMock()
        mock_element.is_visible = AsyncMock(return_value=True)

        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="button.buy", check_exists=True, check_visible=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is True
        mock_element.is_visible.assert_called_once()

    @pytest.mark.asyncio
    async def test_visibility_check_hidden(self, extractor, mock_page):
        """Test visibility check when element is hidden."""
        mock_element = MagicMock()
        mock_element.is_visible = AsyncMock(return_value=False)

        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="button.buy", check_exists=True, check_visible=True)
        result = await extractor._extract_with_selector(mock_page, config)

        assert result is False

    @pytest.mark.asyncio
    async def test_text_mode_inner_text(self, extractor, mock_page):
        """Test inner_text mode (visible text only)."""
        mock_element = MagicMock()
        mock_element.inner_text = AsyncMock(return_value="Visible Text")

        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="div", text_mode="inner_text")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "Visible Text"
        mock_element.inner_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_mode_text_content(self, extractor, mock_page):
        """Test text_content mode (all text including hidden)."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="All Text Including Hidden")

        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(selector="div", text_mode="text_content")
        result = await extractor._extract_with_selector(mock_page, config)

        assert result == "All Text Including Hidden"
        mock_element.text_content.assert_called_once()

    def test_invalid_text_mode(self):
        """Test that invalid text_mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid text_mode"):
            SelectorConfig(selector="div", text_mode="invalid")

    def test_regex_extract_simple(self):
        """Test regex extraction with simple pattern."""
        config = SelectorConfig(selector="div", regex_extract=r"(\d+\.?\d*)\s*kg")
        result = SelectorExtractor._apply_regex_processing("Weight: 2.5 kg", config)

        assert result == "2.5"

    def test_regex_extract_no_groups(self):
        """Test regex extraction without capture groups."""
        config = SelectorConfig(selector="div", regex_extract=r"\d+")
        result = SelectorExtractor._apply_regex_processing("Price: 25 euros", config)

        assert result == "25"

    def test_regex_extract_no_match(self):
        """Test regex extraction when pattern doesn't match."""
        config = SelectorConfig(selector="div", regex_extract=r"\d+")
        result = SelectorExtractor._apply_regex_processing("No numbers here", config)

        assert result == ""

    def test_regex_extract_invalid_pattern(self):
        """Test regex extraction with invalid pattern."""
        config = SelectorConfig(selector="div", regex_extract=r"[invalid(")
        result = SelectorExtractor._apply_regex_processing("Some text", config)

        # Should return original value on error
        assert result == "Some text"

    def test_regex_replace_simple(self):
        """Test regex replacement."""
        config = SelectorConfig(
            selector="div",
            regex_replace={"pattern": r"€\s*", "replacement": ""},
        )
        result = SelectorExtractor._apply_regex_processing("€ 19.99", config)

        assert result == "19.99"

    def test_regex_replace_multiple_occurrences(self):
        """Test regex replacement with multiple matches."""
        config = SelectorConfig(
            selector="div",
            regex_replace={"pattern": r"\s+", "replacement": " "},
        )
        result = SelectorExtractor._apply_regex_processing("Too    many    spaces", config)

        assert result == "Too many spaces"

    def test_regex_replace_invalid_pattern(self):
        """Test regex replacement with invalid pattern."""
        config = SelectorConfig(
            selector="div",
            regex_replace={"pattern": r"[invalid(", "replacement": ""},
        )
        result = SelectorExtractor._apply_regex_processing("Some text", config)

        # Should return original value on error
        assert result == "Some text"

    def test_regex_extract_and_replace_combined(self):
        """Test combining regex extract and replace."""
        config = SelectorConfig(
            selector="div",
            regex_extract=r"Price:\s*(.+)",
            regex_replace={"pattern": r"€\s*", "replacement": ""},
        )
        # First extract "€ 19.99", then replace "€ " → ""
        result = SelectorExtractor._apply_regex_processing("Price: € 19.99 (incl VAT)", config)

        assert result == "19.99 (incl VAT)"

    def test_parse_config_with_all_advanced_features(self):
        """Test parsing config with all advanced features."""
        config = SelectorExtractor.parse_selector_config(
            {
                "selector": ".price",
                "wait_for": True,
                "wait_timeout": 10000,
                "text_mode": "inner_text",
                "check_visible": True,
                "regex_extract": r"(\d+\.?\d*)",
                "regex_replace": {"pattern": r",", "replacement": "."},
            }
        )

        assert config.wait_for is True
        assert config.wait_timeout == 10000
        assert config.text_mode == "inner_text"
        assert config.check_visible is True
        assert config.regex_extract == r"(\d+\.?\d*)"
        assert config.regex_replace == {"pattern": r",", "replacement": "."}

    @pytest.mark.asyncio
    async def test_full_advanced_extraction_flow(self, extractor, mock_page):
        """Test complete extraction with multiple advanced features."""
        mock_element = MagicMock()
        mock_element.inner_text = AsyncMock(return_value="Price: € 1.234,56")
        mock_element.is_visible = AsyncMock(return_value=True)

        mock_page.wait_for_selector = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        config = SelectorConfig(
            selector=".dynamic-price",
            wait_for=True,
            wait_timeout=3000,
            text_mode="inner_text",
            regex_extract=r"€\s*([\d.,]+)",
            regex_replace={"pattern": r"\.", "replacement": ""},
        )

        result = await extractor._extract_with_selector(mock_page, config)

        # Extract "1.234,56" then replace "." → "" = "1234,56"
        assert result == "1234,56"
        mock_page.wait_for_selector.assert_called_once()
        mock_element.inner_text.assert_called_once()
