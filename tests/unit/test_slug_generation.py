from src.utils.slug import generate_slug, normalize_for_comparison


class TestGenerateSlug:
    """Test suite for generate_slug function."""

    def test_basic_slug_generation(self):
        """Test basic slug generation with simple string."""
        assert generate_slug("Weekly Groceries") == "weekly-groceries"
        assert generate_slug("Dog Food") == "dog-food"
        assert generate_slug("Coffee Beans") == "coffee-beans"

    def test_special_characters_removed(self):
        """Test that special characters are removed."""
        assert generate_slug("Dog Food - Premium!!") == "dog-food-premium"
        assert generate_slug("Coffee @ Home #1") == "coffee-home-1"
        assert generate_slug("Weekly $ Groceries") == "weekly-groceries"

    def test_multiple_spaces_collapsed(self):
        """Test that multiple spaces collapse to single hyphen."""
        assert generate_slug("Weekly    Groceries") == "weekly-groceries"
        assert generate_slug("Dog  Food   Premium") == "dog-food-premium"

    def test_multiple_hyphens_collapsed(self):
        """Test that multiple hyphens collapse to single hyphen."""
        assert generate_slug("Coffee--Douwe Egberts") == "coffee-douwe-egberts"
        assert generate_slug("Dog---Food") == "dog-food"
        assert generate_slug("Weekly----Groceries") == "weekly-groceries"

    def test_leading_trailing_hyphens_stripped(self):
        """Test that leading/trailing hyphens are removed."""
        assert generate_slug("-Weekly Groceries-") == "weekly-groceries"
        assert generate_slug("--Dog Food--") == "dog-food"
        assert generate_slug("---Coffee Beans---") == "coffee-beans"

    def test_mixed_case_converted_to_lowercase(self):
        """Test that mixed case is converted to lowercase."""
        assert generate_slug("WeEkLy GrOcErIeS") == "weekly-groceries"
        assert generate_slug("DOG FOOD") == "dog-food"
        assert generate_slug("CoffeeBeans") == "coffeebeans"

    def test_empty_string(self):
        """Test that empty string returns empty string."""
        assert generate_slug("") == ""

    def test_only_special_characters(self):
        """Test string with only special characters."""
        assert generate_slug("!!!@@##$$") == ""
        assert generate_slug("---") == ""

    def test_numbers_preserved(self):
        """Test that numbers are preserved in slugs."""
        assert generate_slug("Group 123") == "group-123"
        assert generate_slug("Product 2025") == "product-2025"

    def test_underscores_converted_to_hyphens(self):
        """Test that underscores are converted to hyphens."""
        assert generate_slug("weekly_groceries") == "weekly-groceries"
        assert generate_slug("dog_food_premium") == "dog-food-premium"

    def test_length_limit(self):
        """Test that slug is limited to 100 characters."""
        long_name = "A" * 150
        slug = generate_slug(long_name)
        assert len(slug) == 100

    def test_real_world_examples(self):
        """Test with real-world product group names."""
        assert generate_slug("Weekly Groceries - Store-A") == "weekly-groceries-store-a"
        assert generate_slug("Coffee - Douwe Egberts (500g)") == "coffee-douwe-egberts-500g"
        assert generate_slug("Dog Food Comparison 2025!") == "dog-food-comparison-2025"
        assert generate_slug("Store-B - Weekly List") == "store-b-weekly-list"


class TestNormalizeForComparison:
    """Test suite for normalize_for_comparison function."""

    def test_basic_normalization(self):
        """Test basic normalization."""
        assert normalize_for_comparison("Weekly Groceries") == "weekly groceries"
        assert normalize_for_comparison("Dog Food") == "dog food"

    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        assert normalize_for_comparison("  Weekly Groceries  ") == "weekly groceries"
        assert normalize_for_comparison("\tDog Food\n") == "dog food"

    def test_lowercase_conversion(self):
        """Test case-insensitive conversion."""
        assert normalize_for_comparison("WEEKLY GROCERIES") == "weekly groceries"
        assert normalize_for_comparison("WeEkLy GrOcErIeS") == "weekly groceries"

    def test_preserves_internal_structure(self):
        """Test that internal structure (spaces, punctuation) is preserved."""
        assert normalize_for_comparison("Dog-Food") == "dog-food"
        assert normalize_for_comparison("Coffee @ Home") == "coffee @ home"
        assert normalize_for_comparison("Weekly Groceries!") == "weekly groceries!"

    def test_empty_string(self):
        """Test empty string handling."""
        assert normalize_for_comparison("") == ""
        assert normalize_for_comparison("   ") == ""


class TestSlugEdgeCases:
    """Test edge cases for slug generation."""

    def test_unicode_characters(self):
        """Test handling of unicode/non-ASCII characters."""
        slug = generate_slug("Café Latte")
        assert slug == "café-latte"  # é is preserved as word character

    def test_mixed_symbols_and_text(self):
        """Test mixed symbols and text."""
        assert generate_slug("100% Organic!!! Product###") == "100-organic-product"
        assert generate_slug("$$$Money$$$ Saver") == "money-saver"

    def test_consecutive_different_separators(self):
        """Test consecutive different separator types."""
        assert generate_slug("Dog  - - Food") == "dog-food"
        assert generate_slug("Weekly _ - _ Groceries") == "weekly-groceries"

    def test_only_numbers(self):
        """Test slug with only numbers."""
        assert generate_slug("12345") == "12345"
        assert generate_slug("2025") == "2025"

    def test_combination_patterns(self):
        """Test various combination patterns."""
        assert generate_slug("!Weekly! @Groceries@ #2025#") == "weekly-groceries-2025"
        assert generate_slug("Dog___Food---Premium") == "dog-food-premium"
