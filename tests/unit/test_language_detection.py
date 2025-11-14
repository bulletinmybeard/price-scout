from src.utils.product_parser import (
    _get_country_language_map,
    _get_flat_variant_list,
    extract_variants,
    parse_product_details,
)


class TestCountryToLanguageMapping:
    """Test country-to-language mapping from YAML config."""

    def test_common_european_countries(self):
        """Common European countries should map correctly."""
        country_map = _get_country_language_map()
        assert country_map["NL"] == "nl"  # Netherlands -> Dutch
        assert country_map["DE"] == "de"  # Germany -> German
        assert country_map["FR"] == "fr"  # France -> French
        assert country_map["ES"] == "es"  # Spain -> Spanish
        assert country_map["IT"] == "it"  # Italy -> Italian

    def test_english_speaking_countries(self):
        """English-speaking countries should map to 'en'."""
        country_map = _get_country_language_map()
        assert country_map["GB"] == "en"  # United Kingdom
        assert country_map["US"] == "en"  # United States
        assert country_map["CA"] == "en"  # Canada
        assert country_map["AU"] == "en"  # Australia

    def test_multilingual_countries_have_primary_language(self):
        """Multilingual countries should map to primary language."""
        country_map = _get_country_language_map()
        assert country_map["BE"] == "nl"  # Belgium (also French, but Dutch primary)
        assert country_map["CH"] == "de"  # Switzerland (also French/Italian)


class TestGetFlatVariantListLanguageSpecific:
    """Test language-specific variant list generation."""

    def test_get_dutch_colors_only(self):
        """Should return only Dutch color variants when language='nl'."""
        colors = _get_flat_variant_list("colors", language="nl")
        assert "rood" in colors  # Dutch
        assert "blauw" in colors  # Dutch
        # Should NOT contain English or German
        assert "red" not in colors
        assert "rot" not in colors

    def test_get_english_flavors_only(self):
        """Should return only English flavor variants when language='en'."""
        flavors = _get_flat_variant_list("flavors", language="en")
        assert "chocolate" in flavors  # English
        assert "vanilla" in flavors  # English
        # Should NOT contain Dutch or German
        assert "chocolade" not in flavors
        assert "schokolade" not in flavors

    def test_get_german_types_only(self):
        """Should return only German type variants when language='de'."""
        types = _get_flat_variant_list("types", language="de")
        assert "biologisch" in types  # German
        assert "vegan" in types  # German
        # Should NOT contain English-only variants
        assert "organic" not in types

    def test_get_all_languages_when_no_language_specified(self):
        """Should return all languages when language=None (backward compatible)."""
        colors = _get_flat_variant_list("colors", language=None)
        # Should contain variants from all languages
        assert "red" in colors  # English
        assert "rood" in colors  # Dutch
        assert "rot" in colors  # German

    def test_get_nonexistent_language_returns_empty(self):
        """Should return empty list for unsupported language."""
        colors = _get_flat_variant_list("colors", language="fr")  # French not in defaults
        assert colors == []


class TestExtractVariantsLanguageSpecific:
    """Test language-specific variant extraction."""

    def test_extract_dutch_color_with_dutch_language(self):
        """Should find Dutch color when language='nl'."""
        result = extract_variants("Rood appelsap", language="nl")
        assert result["variant_color"] == "rood"
        assert result["variant_flavor"] is None
        assert result["variant_type"] is None

    def test_extract_german_flavor_with_german_language(self):
        """Should find German flavor when language='de'."""
        result = extract_variants("Schokolade kekse", language="de")
        assert result["variant_color"] is None
        assert result["variant_flavor"] == "schokolade"
        assert result["variant_type"] is None

    def test_extract_english_type_with_english_language(self):
        """Should find English type when language='en'."""
        result = extract_variants("Organic cookies", language="en")
        assert result["variant_color"] is None
        assert result["variant_flavor"] is None
        assert result["variant_type"] == "organic"

    def test_extract_does_not_match_wrong_language(self):
        """Should NOT find variant from different language when language specified."""
        # "rood" is Dutch for "red", not in English variants
        result = extract_variants("Rood appelsap", language="en")
        assert result["variant_color"] is None  # No match in English

    def test_extract_all_languages_when_no_language_specified(self):
        """Should search all languages when language=None (backward compatible)."""
        # Should find Dutch variant even without language specified
        result = extract_variants("Rood appelsap", language=None)
        assert result["variant_color"] == "rood"

    def test_extract_performance_improvement_with_language(self):
        """Language-specific extraction should be faster (fewer variants to check)."""
        # This is more of a documentation test showing the performance benefit
        # With language='nl': ~5 variants per category
        # Without language: ~20-30 variants per category (all languages combined)

        nl_colors = _get_flat_variant_list("colors", language="nl")
        all_colors = _get_flat_variant_list("colors", language=None)

        # Dutch should have significantly fewer variants than all languages
        assert len(nl_colors) < len(all_colors)
        assert len(nl_colors) < 10  # Dutch has 5 colors in defaults
        assert len(all_colors) > 15  # Combined across languages (en + nl + de)


class TestParseProductDetailsLanguageAware:
    """Test parse_product_details with language and country parameters."""

    def test_parse_with_explicit_language(self):
        """Should use explicit language parameter for variant extraction."""
        result = parse_product_details(
            name="Chocolade koekjes 500g",
            language="nl",  # Explicit Dutch
        )
        assert result["variant_flavor"] == "chocolade"  # Dutch flavor
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "g"

    def test_parse_with_country_fallback(self):
        """Should use country-to-language mapping when language not provided."""
        result = parse_product_details(
            name="Schokolade kekse 500g",
            country="DE",  # German country
        )
        assert result["variant_flavor"] == "schokolade"  # German flavor matched
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "g"

    def test_parse_language_overrides_country(self):
        """Explicit language should override country mapping."""
        # Language='nl' should be used, not country='DE'
        result = parse_product_details(name="Chocolade koekjes", language="nl", country="DE")
        assert result["variant_flavor"] == "chocolade"  # Dutch matched, not German

    def test_parse_without_language_or_country_searches_all(self):
        """Should search all languages when neither language nor country provided."""
        result = parse_product_details(name="Schokolade kekse")
        # Should still find German flavor by searching all languages
        assert result["variant_flavor"] == "schokolade"

    def test_parse_combined_amount_and_variants(self):
        """Should extract both amount and language-specific variants."""
        result = parse_product_details(
            name="Biologisch appelsap 1 liter",
            language="de",  # German
        )
        assert result["variant_type"] == "biologisch"  # German type
        assert result["amount_value"] == 1.0
        assert result["amount_unit"] == "l"

    def test_parse_multipack_with_dutch_language(self):
        """Should handle multi-pack and Dutch variants together."""
        result = parse_product_details(name="6 x 330ml Rood appelsap", language="nl")
        assert result["pack_quantity"] == 6
        assert result["amount_value"] == 330.0
        assert result["amount_unit"] == "ml"
        assert result["variant_color"] == "rood"  # Dutch color

    def test_parse_unknown_country_code_falls_back_to_all_languages(self):
        """Unknown country code should fall back to searching all languages."""
        result = parse_product_details(name="Chocolate cookies", country="XX")
        # Should still find English flavor by searching all languages
        assert result["variant_flavor"] == "chocolate"

    def test_parse_empty_language_string_treated_as_none(self):
        """Empty string for language should not filter (treated as falsy)."""
        # Empty string should be treated as falsy and fall back to all languages
        result = parse_product_details(name="Chocolate cookies", language="")

        # Empty string is falsy in the if-check, so it won't filter by language
        # Should find the flavor by searching all languages
        assert result["variant_flavor"] == "chocolate"


class TestLanguageFallbackHierarchy:
    """Test the complete language fallback hierarchy."""

    def test_hierarchy_explicit_language_wins(self):
        """Explicit language should always win over country mapping."""
        # Even with country='DE' (German), language='en' should be used
        result = parse_product_details(name="Chocolate cookies", language="en", country="DE")
        assert result["variant_flavor"] == "chocolate"  # English matched

    def test_hierarchy_country_mapping_second(self):
        """Country mapping should be used when language not provided."""
        result = parse_product_details(name="Chocolade koekjes", country="NL")
        assert result["variant_flavor"] == "chocolade"  # Dutch matched via NL->nl

    def test_hierarchy_all_languages_fallback(self):
        """Should search all languages when neither language nor country provided."""
        # No language or country - should still find variants
        result = parse_product_details(name="Schokolade kekse")
        assert result["variant_flavor"] == "schokolade"  # Found in all-languages search


class TestBackwardCompatibility:
    """Ensure all new language features are backward compatible."""

    def test_existing_code_without_language_parameter_works(self):
        """Code not using language parameter should work as before."""
        # This simulates existing code that doesn't know about language parameter
        result = extract_variants("Chocolate cookies")
        assert result["variant_flavor"] == "chocolate"

    def test_parse_product_details_without_new_parameters(self):
        """parse_product_details without language/country should work as before."""
        result = parse_product_details(name="Organic chocolate cookies 500g")
        assert result["variant_flavor"] == "chocolate"
        assert result["variant_type"] == "organic"
        assert result["amount_value"] == 500.0
        assert result["amount_unit"] == "g"

    def test_all_original_tests_still_pass(self):
        """Original test cases should still pass with new implementation."""
        # Example from original tests
        result = parse_product_details(name="Douwe Egberts Koffiepads Espresso", weight="180 GRM")
        assert result["amount_value"] == 180.0
        assert result["amount_unit"] == "g"  # Normalized from GRM
