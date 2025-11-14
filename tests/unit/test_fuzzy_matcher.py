import pytest

from src.utils.fuzzy_matcher import (
    calculate_similarity,
    find_similar_groups,
    format_similarity_percentage,
)


class TestCalculateSimilarity:
    """Test suite for calculate_similarity function."""

    def test_identical_strings(self):
        """Test similarity of identical strings."""
        similarity = calculate_similarity("Dog Food", "Dog Food")
        assert similarity == 1.0

    def test_completely_different_strings(self):
        """Test similarity of completely different strings."""
        similarity = calculate_similarity("Dog Food", "Cat Litter")
        assert similarity < 0.5

    def test_minor_typo(self):
        """Test similarity with minor typo."""
        similarity = calculate_similarity("Dog Food", "Doog Food")
        assert similarity > 0.8

    def test_case_insensitivity(self):
        """Test that comparison is case-insensitive."""
        similarity = calculate_similarity("Dog Food", "dog food")
        assert similarity == 1.0  # Should be identical after normalization

    def test_extra_space(self):
        """Test similarity with extra spaces."""
        similarity = calculate_similarity("Dog Food", "Dog  Food")
        assert similarity > 0.9

    def test_hyphen_vs_space(self):
        """Test hyphen vs space in names."""
        similarity = calculate_similarity("Dog-Food", "Dog Food")
        assert similarity >= 0.9

    def test_empty_strings(self):
        """Test with empty strings."""
        assert calculate_similarity("", "") == 0.0
        assert calculate_similarity("Dog Food", "") == 0.0
        assert calculate_similarity("", "Dog Food") == 0.0

    def test_real_world_typos(self):
        """Test with real-world typo scenarios."""
        similarity1 = calculate_similarity("Weekly Groceries", "Weekly Groceriess")
        assert similarity1 > 0.8

        similarity2 = calculate_similarity("Dog Food Premium", "Dog Food Premiumm")
        assert similarity2 > 0.8

        similarity3 = calculate_similarity("Coffee Beans", "Cofefe Beans")
        assert similarity3 > 0.7


class TestFindSimilarGroups:
    """Test suite for find_similar_groups function."""

    @pytest.fixture
    def sample_groups(self):
        """Sample product groups for testing."""
        return [
            {"group_id": 1, "name": "Dog Food", "slug": "dog-food"},
            {"group_id": 2, "name": "Dog Food Premium", "slug": "dog-food-premium"},
            {"group_id": 3, "name": "Cat Litter", "slug": "cat-litter"},
            {"group_id": 4, "name": "Weekly Groceries", "slug": "weekly-groceries"},
            {"group_id": 5, "name": "Coffee Beans", "slug": "coffee-beans"},
        ]

    def test_find_exact_match(self, sample_groups):
        """Test finding exact match."""
        matches = find_similar_groups("Dog Food", sample_groups, threshold=0.8)
        assert len(matches) >= 1
        assert matches[0][0]["name"] == "Dog Food"
        assert matches[0][1] == 1.0  # Perfect match

    def test_find_typo_match(self, sample_groups):
        """Test finding match with typo."""
        matches = find_similar_groups("Doog Food", sample_groups, threshold=0.8)
        assert len(matches) >= 1
        assert any(m[0]["name"] == "Dog Food" for m in matches)

    def test_find_multiple_similar(self, sample_groups):
        """Test finding multiple similar groups."""
        matches = find_similar_groups("Dog Food", sample_groups, threshold=0.7)
        names = [m[0]["name"] for m in matches]
        assert "Dog Food" in names
        assert len(matches) >= 1

    def test_no_matches_below_threshold(self, sample_groups):
        """Test that no matches returned below threshold."""
        matches = find_similar_groups("Completely Different Thing", sample_groups, threshold=0.9)
        assert len(matches) == 0

    def test_limit_parameter(self, sample_groups):
        """Test that limit parameter works."""
        matches = find_similar_groups("Dog Food", sample_groups, threshold=0.5, limit=2)
        assert len(matches) <= 2

    def test_sorted_by_similarity(self, sample_groups):
        """Test that results are sorted by similarity (descending)."""
        matches = find_similar_groups("Dog Food", sample_groups, threshold=0.5)
        if len(matches) > 1:
            for i in range(len(matches) - 1):
                assert matches[i][1] >= matches[i + 1][1]

    def test_case_insensitive_matching(self, sample_groups):
        """Test that matching is case-insensitive."""
        matches_lower = find_similar_groups("dog food", sample_groups, threshold=0.8)
        matches_upper = find_similar_groups("DOG FOOD", sample_groups, threshold=0.8)
        matches_mixed = find_similar_groups("DoG FoOd", sample_groups, threshold=0.8)

        assert len(matches_lower) == len(matches_upper) == len(matches_mixed)

    def test_empty_input(self, sample_groups):
        """Test with empty input name."""
        matches = find_similar_groups("", sample_groups, threshold=0.8)
        assert len(matches) == 0

    def test_empty_groups_list(self):
        """Test with empty groups list."""
        matches = find_similar_groups("Dog Food", [], threshold=0.8)
        assert len(matches) == 0

    def test_groups_without_name_key(self):
        """Test handling of groups without 'name' key."""
        invalid_groups = [{"group_id": 1}]  # Missing 'name' key
        matches = find_similar_groups("Dog Food", invalid_groups, threshold=0.8)
        assert len(matches) == 0


class TestFormatSimilarityPercentage:
    """Test suite for format_similarity_percentage function."""

    def test_perfect_match(self):
        """Test formatting 100% match."""
        assert format_similarity_percentage(1.0) == "100%"

    def test_high_similarity(self):
        """Test formatting high similarity."""
        assert format_similarity_percentage(0.85) == "85%"
        assert format_similarity_percentage(0.92) == "92%"

    def test_low_similarity(self):
        """Test formatting low similarity."""
        assert format_similarity_percentage(0.42) == "42%"
        assert format_similarity_percentage(0.05) == "5%"

    def test_zero_similarity(self):
        """Test formatting 0% match."""
        assert format_similarity_percentage(0.0) == "0%"

    def test_rounding(self):
        """Test that percentages are properly rounded."""
        assert format_similarity_percentage(0.855) == "85%"  # Rounds down
        assert format_similarity_percentage(0.856) == "85%"  # int() truncates


class TestRealWorldScenarios:
    """Test real-world fuzzy matching scenarios."""

    def test_weekly_groceries_typo(self):
        """Test scenario from user's example: 'Weekly Groceries' vs 'Weekly Groceriess'."""
        groups = [
            {"group_id": 1, "name": "Weekly Groceries", "slug": "weekly-groceries"},
            {"group_id": 2, "name": "Monthly Shopping", "slug": "monthly-shopping"},
        ]

        matches = find_similar_groups("Weekly Groceriess", groups, threshold=0.8, limit=3)

        assert len(matches) >= 1
        assert matches[0][0]["name"] == "Weekly Groceries"
        assert matches[0][1] > 0.8

    def test_dog_food_variations(self):
        """Test matching various dog food group names."""
        groups = [
            {"group_id": 1, "name": "Dog Food", "slug": "dog-food"},
            {"group_id": 2, "name": "Dog Food Premium", "slug": "dog-food-premium"},
            {"group_id": 3, "name": "Dog Food - Budget", "slug": "dog-food-budget"},
        ]

        matches1 = find_similar_groups("Doog Food", groups, threshold=0.8, limit=3)
        assert len(matches1) >= 1
        assert "Dog Food" in [m[0]["name"] for m in matches1]

        matches2 = find_similar_groups("dog food", groups, threshold=0.8, limit=3)
        assert len(matches2) >= 1

    def test_coffee_variations(self):
        """Test coffee product group variations."""
        groups = [
            {"group_id": 1, "name": "Coffee - Douwe Egberts", "slug": "coffee-douwe-egberts"},
            {"group_id": 2, "name": "Coffee Beans", "slug": "coffee-beans"},
            {"group_id": 3, "name": "Tea Selection", "slug": "tea-selection"},
        ]

        matches = find_similar_groups("Coffee - Douwe Egbert", groups, threshold=0.8)
        assert len(matches) >= 1
        assert matches[0][0]["name"] == "Coffee - Douwe Egberts"

    def test_no_false_positives(self):
        """Test that completely different names don't match."""
        groups = [
            {"group_id": 1, "name": "Dog Food", "slug": "dog-food"},
            {"group_id": 2, "name": "Cat Litter", "slug": "cat-litter"},
            {"group_id": 3, "name": "Fish Tank Supplies", "slug": "fish-tank-supplies"},
        ]

        matches = find_similar_groups("Weekly Groceries", groups, threshold=0.8)
        assert len(matches) == 0
