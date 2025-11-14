from src.utils.product_parser import (
    extract_amount_and_unit,
    extract_pack_info,
    extract_variants,
    normalize_unit_code,
    parse_product_details,
)


class TestNormalizeUnitCode:
    """Test UN/CEFACT code normalization."""

    def test_normalize_un_cefact_weight_codes(self):
        """UN/CEFACT weight codes are normalized."""
        assert normalize_unit_code("KGM") == "kg"
        assert normalize_unit_code("GRM") == "g"
        assert normalize_unit_code("MGM") == "mg"
        assert normalize_unit_code("TNE") == "t"

    def test_normalize_un_cefact_volume_codes(self):
        """UN/CEFACT volume codes are normalized."""
        assert normalize_unit_code("LTR") == "l"
        assert normalize_unit_code("MLT") == "ml"
        assert normalize_unit_code("CLT") == "cl"
        assert normalize_unit_code("DLT") == "dl"

    def test_normalize_un_cefact_length_codes(self):
        """UN/CEFACT length codes are normalized."""
        assert normalize_unit_code("MTR") == "m"
        assert normalize_unit_code("CMT") == "cm"
        assert normalize_unit_code("MMT") == "mm"
        assert normalize_unit_code("KMT") == "km"

    def test_normalize_common_variations(self):
        """Common unit variations are normalized."""
        assert normalize_unit_code("kilo") == "kg"
        assert normalize_unit_code("kilogram") == "kg"
        assert normalize_unit_code("gram") == "g"
        assert normalize_unit_code("liter") == "l"
        assert normalize_unit_code("milliliter") == "ml"
        assert normalize_unit_code("stuks") == "st"
        assert normalize_unit_code("stuk") == "st"

    def test_normalize_case_insensitive(self):
        """Normalization is case insensitive."""
        assert normalize_unit_code("kgm") == "kg"
        assert normalize_unit_code("Kgm") == "kg"
        assert normalize_unit_code("LITER") == "l"
        assert normalize_unit_code("Stuks") == "st"

    def test_normalize_unknown_unit_lowercase(self):
        """Unknown units are returned as lowercase."""
        assert normalize_unit_code("UNKNOWN") == "unknown"
        assert normalize_unit_code("XYZ") == "xyz"

    def test_normalize_empty_string(self):
        """Empty string returns empty string."""
        assert normalize_unit_code("") == ""

    def test_normalize_already_normalized(self):
        """Already normalized units pass through."""
        assert normalize_unit_code("kg") == "kg"
        assert normalize_unit_code("ml") == "ml"
        assert normalize_unit_code("g") == "g"


class TestExtractAmountAndUnit:
    """Test amount and unit extraction from text."""

    def test_extract_weight_kilogram(self):
        """Extract kilogram amounts."""
        assert extract_amount_and_unit("2 kg") == (2.0, "kg")
        assert extract_amount_and_unit("1.5 kg") == (1.5, "kg")
        assert extract_amount_and_unit("10kg") == (10.0, "kg")
        assert extract_amount_and_unit("2,5 kg") == (2.5, "kg")  # European decimal

    def test_extract_weight_gram(self):
        """Extract gram amounts."""
        assert extract_amount_and_unit("500 g") == (500.0, "g")
        assert extract_amount_and_unit("250g") == (250.0, "g")
        assert extract_amount_and_unit("1.5 g") == (1.5, "g")

    def test_extract_volume_liter(self):
        """Extract liter amounts."""
        assert extract_amount_and_unit("1 l") == (1.0, "l")
        assert extract_amount_and_unit("2.5 l") == (2.5, "l")
        assert extract_amount_and_unit("1l") == (1.0, "l")

    def test_extract_volume_milliliter(self):
        """Extract milliliter amounts."""
        assert extract_amount_and_unit("500 ml") == (500.0, "ml")
        assert extract_amount_and_unit("330ml") == (330.0, "ml")
        assert extract_amount_and_unit("750 ml") == (750.0, "ml")

    def test_extract_volume_centiliter(self):
        """Extract centiliter amounts."""
        assert extract_amount_and_unit("75 cl") == (75.0, "cl")
        assert extract_amount_and_unit("100cl") == (100.0, "cl")

    def test_extract_count_stuks(self):
        """Extract count in stuks."""
        assert extract_amount_and_unit("6 stuks") == (6.0, "st")
        assert extract_amount_and_unit("12 stuk") == (12.0, "st")
        assert extract_amount_and_unit("1 st") == (1.0, "st")

    def test_extract_from_product_name(self):
        """Extract from full product name."""
        assert extract_amount_and_unit("Store-A Cashewnoten Gezouten 500 g") == (500.0, "g")
        assert extract_amount_and_unit("Pepsi Zero Sugar Cherry 1.5 L") == (1.5, "l")
        assert extract_amount_and_unit("Coffee Beans Organic 10 kg") == (10.0, "kg")

    def test_extract_range_takes_first_value(self):
        """Range format returns first value."""
        assert extract_amount_and_unit("100-200g") == (100.0, "g")
        assert extract_amount_and_unit("1-2 kg") == (1.0, "kg")
        assert extract_amount_and_unit("250-500 ml") == (250.0, "ml")

    def test_extract_case_insensitive(self):
        """Extraction is case insensitive."""
        assert extract_amount_and_unit("500 G") == (500.0, "g")
        assert extract_amount_and_unit("1 L") == (1.0, "l")
        assert extract_amount_and_unit("2 KG") == (2.0, "kg")

    def test_extract_with_extra_whitespace(self):
        """Handles extra whitespace."""
        assert extract_amount_and_unit("500   g") == (500.0, "g")
        assert extract_amount_and_unit("  1 l  ") == (1.0, "l")

    def test_extract_no_match_returns_none(self):
        """No match returns (None, None)."""
        assert extract_amount_and_unit("No amount here") == (None, None)
        assert extract_amount_and_unit("Product Name") == (None, None)
        assert extract_amount_and_unit("") == (None, None)

    def test_extract_priority_weight_over_count(self):
        """Weight/volume has priority over count."""
        # Should extract "500 g" not "1 st"
        result = extract_amount_and_unit("Product 1 st 500 g")
        assert result == (500.0, "g")


class TestExtractPackInfo:
    """Test multi-pack information extraction."""

    def test_extract_multipack_with_amount(self):
        """Extract multi-pack with unit amount."""
        assert extract_pack_info("Beer 6 x 330ml") == (6, 330.0, "ml")
        assert extract_pack_info("Coffee 3 x 1kg") == (3, 1.0, "kg")
        assert extract_pack_info("Yogurt 12 x 125g") == (12, 125.0, "g")

    def test_extract_multipack_with_decimal(self):
        """Extract multi-pack with decimal amount."""
        assert extract_pack_info("Milk 4 x 1.5l") == (4, 1.5, "l")
        assert extract_pack_info("Juice 6 x 0.5l") == (6, 0.5, "l")

    def test_extract_multipack_european_decimal(self):
        """Extract multi-pack with European decimal (comma)."""
        assert extract_pack_info("Soda 6 x 1,5l") == (6, 1.5, "l")
        assert extract_pack_info("Water 12 x 0,5l") == (12, 0.5, "l")

    def test_extract_pack_count_only(self):
        """Extract pack count without unit amount."""
        assert extract_pack_info("Toilet Paper 12-pack") == (12, None, None)
        assert extract_pack_info("Batteries 6-pack") == (6, None, None)
        assert extract_pack_info("Cookies 6x") == (6, None, None)

    def test_extract_single_item_returns_one(self):
        """Single items return pack_quantity=1."""
        assert extract_pack_info("Single Beer 330ml") == (1, None, None)
        assert extract_pack_info("Coffee 1kg") == (1, None, None)
        assert extract_pack_info("Product Name") == (1, None, None)

    def test_extract_case_insensitive(self):
        """Pack extraction is case insensitive."""
        assert extract_pack_info("BEER 6 X 330ML") == (6, 330.0, "ml")
        assert extract_pack_info("Coffee 3 X 1KG") == (3, 1.0, "kg")

    def test_extract_with_whitespace_variations(self):
        """Handles various whitespace patterns."""
        assert extract_pack_info("Beer 6x330ml") == (6, 330.0, "ml")
        assert extract_pack_info("Beer 6 x 330ml") == (6, 330.0, "ml")
        assert extract_pack_info("Beer 6  x  330ml") == (6, 330.0, "ml")

    def test_extract_no_pack_info_returns_one(self):
        """No pack info returns (1, None, None)."""
        assert extract_pack_info("Regular Product") == (1, None, None)
        assert extract_pack_info("") == (1, None, None)


class TestExtractVariants:
    """Test variant information extraction (color, flavor, type)."""

    def test_extract_color_english(self):
        """Extract color in English."""
        result = extract_variants("Paint Red Matt")
        assert result["variant_color"] == "red"

        result = extract_variants("Shirt Blue Large")
        assert result["variant_color"] == "blue"

        result = extract_variants("Car Black Metallic")
        assert result["variant_color"] == "black"

    def test_extract_color_dutch(self):
        """Extract color in Dutch."""
        result = extract_variants("Verf Rood Mat")
        assert result["variant_color"] == "rood"

        result = extract_variants("Shirt Blauw Groot")
        assert result["variant_color"] == "blauw"

    def test_extract_flavor_english(self):
        """Extract flavor in English."""
        result = extract_variants("Yogurt Strawberry")
        assert result["variant_flavor"] == "strawberry"

        result = extract_variants("Ice Cream Chocolate Chip")
        assert result["variant_flavor"] == "chocolate"

        result = extract_variants("Drink Lemon Lime")
        assert result["variant_flavor"] == "lemon"

    def test_extract_flavor_dutch(self):
        """Extract flavor in Dutch."""
        result = extract_variants("Yoghurt Aardbei")
        assert result["variant_flavor"] == "aardbei"

        result = extract_variants("Drank Citroen")
        assert result["variant_flavor"] == "citroen"

    def test_extract_type_organic(self):
        """Extract organic/bio type."""
        result = extract_variants("Coffee Beans Organic")
        assert result["variant_type"] == "organic"

        result = extract_variants("Milk Biologisch")
        assert result["variant_type"] == "biologisch"

        result = extract_variants("Eggs Bio")
        assert result["variant_type"] == "bio"

    def test_extract_type_diet(self):
        """Extract diet/light type."""
        result = extract_variants("Soda Zero Sugar")
        assert result["variant_type"] == "zero"

        result = extract_variants("Yogurt Light")
        assert result["variant_type"] == "light"

        result = extract_variants("Milk Sugar-free")
        assert result["variant_type"] == "sugar-free"

    def test_extract_type_dietary_restrictions(self):
        """Extract dietary restriction types."""
        result = extract_variants("Bread Gluten-free")
        assert result["variant_type"] == "gluten-free"

        result = extract_variants("Cheese Lactose-free")
        assert result["variant_type"] == "lactose-free"

        result = extract_variants("Burger Vegan")
        assert result["variant_type"] == "vegan"

    def test_extract_multiple_variants(self):
        """Extract multiple variants from same text."""
        result = extract_variants("Yogurt Strawberry Organic")
        assert result["variant_flavor"] == "strawberry"
        assert result["variant_type"] == "organic"
        assert result["variant_color"] is None

        result = extract_variants("Paint Red Matt Eco")
        assert result["variant_color"] == "red"
        assert result["variant_type"] == "eco"

    def test_extract_no_variants_returns_none(self):
        """No variants returns all None."""
        result = extract_variants("Regular Product Name")
        assert result["variant_color"] is None
        assert result["variant_flavor"] is None
        assert result["variant_type"] is None

    def test_extract_empty_string_returns_none(self):
        """Empty string returns all None."""
        result = extract_variants("")
        assert result["variant_color"] is None
        assert result["variant_flavor"] is None
        assert result["variant_type"] is None

    def test_extract_case_insensitive(self):
        """Variant extraction is case insensitive."""
        result = extract_variants("PAINT RED MATT")
        assert result["variant_color"] == "red"

        result = extract_variants("Yogurt STRAWBERRY")
        assert result["variant_flavor"] == "strawberry"

        result = extract_variants("Coffee ORGANIC")
        assert result["variant_type"] == "organic"

    def test_extract_word_boundary_matching(self):
        """Only matches whole words (not substrings)."""
        # "redirect" should not match "red"
        result = extract_variants("Redirect Service")
        assert result["variant_color"] is None

        result = extract_variants("Lightbulb 60W")
        assert result["variant_type"] is None


class TestParseProductDetails:
    """Test the main orchestrator function."""

    def test_parse_multipack_from_name(self):
        """Extract multi-pack info from name."""
        result = parse_product_details("Beer 6 x 330ml")
        assert result["pack_quantity"] == 6
        assert result["amount_value"] == 330.0
        assert result["amount_unit"] == "ml"

    def test_parse_from_weight_field(self):
        """Extract from weight field."""
        result = parse_product_details("Coffee Beans", weight="1 kg")
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "kg"
        assert result["pack_quantity"] == 1

    def test_parse_from_volume_field(self):
        """Extract from volume field."""
        result = parse_product_details("Milk", volume="1 L")
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "l"
        assert result["pack_quantity"] == 1

    def test_parse_un_cefact_from_weight(self):
        """Normalize UN/CEFACT codes in weight field."""
        result = parse_product_details("Coffee Beans", weight="10 KGM")
        assert result["amount_value"] == 10.0
        assert result["amount_unit"] == "kg"

    def test_parse_un_cefact_from_volume(self):
        """Normalize UN/CEFACT codes in volume field."""
        result = parse_product_details("Milk", volume="1 LTR")
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "l"

    def test_parse_priority_weight_over_name(self):
        """Weight field has priority over name."""
        result = parse_product_details("Product 500 g", weight="1 kg")
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "kg"

    def test_parse_priority_volume_over_name(self):
        """Volume field has priority over name."""
        result = parse_product_details("Product 500 ml", volume="1 L")
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "l"

    def test_parse_fallback_to_name(self):
        """Falls back to name if no weight/volume."""
        result = parse_product_details("Product 500 g")
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "g"

    def test_parse_variants_from_name(self):
        """Extract variants from name."""
        result = parse_product_details("Yogurt Strawberry Organic 500 g")
        assert result["variant_flavor"] == "strawberry"
        assert result["variant_type"] == "organic"
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "g"

    def test_parse_complete_example_store_a(self):
        """Example from store-a."""
        result = parse_product_details("Optimel Drinkyoghurt Limoen 0% Vet 1L", volume="1 L")
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "l"
        assert result["pack_quantity"] == 1
        assert result["variant_flavor"] == "limoen"  # Dutch: lime

    def test_parse_complete_example_store_c(self):
        """Example from store-c."""
        result = parse_product_details("Royal Canin Medium Adult 7+ - 10 kg", weight="10 KGM")
        assert result["amount_value"] == 10.0
        assert result["amount_unit"] == "kg"
        assert result["pack_quantity"] == 1

    def test_parse_complete_example_multipack(self):
        """Real example with multi-pack."""
        result = parse_product_details("Cristaline Bronwater 12 x 500 ml")
        assert result["pack_quantity"] == 12
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "ml"

    def test_parse_no_amount_returns_none(self):
        """No amount found returns None values."""
        result = parse_product_details("Product Name")
        assert result["amount_value"] is None
        assert result["amount_unit"] is None
        assert result["pack_quantity"] == 1

    def test_parse_empty_inputs_returns_defaults(self):
        """Empty inputs return default values."""
        result = parse_product_details("", None, None)
        assert result["amount_value"] is None
        assert result["amount_unit"] is None
        assert result["pack_quantity"] == 1
        assert result["variant_color"] is None
        assert result["variant_flavor"] is None
        assert result["variant_type"] is None

    def test_parse_multipack_overrides_name_amount(self):
        """Multi-pack amount takes priority."""
        result = parse_product_details("Water 6 x 500ml 3L Total")
        # Should use "500 ml" from multi-pack, not "3L"
        assert result["pack_quantity"] == 6
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "ml"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_normalize_unit_with_whitespace(self):
        """Unit normalization handles whitespace."""
        assert normalize_unit_code("  kg  ") == "kg"
        assert normalize_unit_code("KGM ") == "kg"

    def test_extract_amount_malformed_decimal(self):
        """Malformed decimal returns None."""
        result = extract_amount_and_unit("1..5 kg")
        # Should not match or should handle gracefully
        # Depending on regex, might match "1" or nothing
        assert result[1] in ["kg", None]  # Either extracts "1 kg" or nothing

    def test_extract_pack_invalid_format(self):
        """Invalid pack format returns single item."""
        assert extract_pack_info("x 330ml") == (1, None, None)
        assert extract_pack_info("6 x") == (6, None, None)
        assert extract_pack_info("6 x abc") == (6, None, None)

    def test_extract_variants_partial_word_match(self):
        """Partial word matches are not extracted."""
        result = extract_variants("Redirect Service")
        assert result["variant_color"] is None

    def test_parse_combined_weight_and_volume(self):
        """Handle products with both weight and volume."""
        result = parse_product_details("Product Name", weight="500 g", volume="1 L")
        # Weight has priority
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "g"

    def test_parse_very_large_numbers(self):
        """Handle very large amounts."""
        result = parse_product_details("Bulk Item 10000 kg")
        assert result["amount_value"] == 10000.0
        assert result["amount_unit"] == "kg"

    def test_parse_very_small_decimals(self):
        """Handle very small decimal amounts."""
        result = parse_product_details("Sample 0.1 g")
        assert result["amount_value"] == 0.1
        assert result["amount_unit"] == "g"
