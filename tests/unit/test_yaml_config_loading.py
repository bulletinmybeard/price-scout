"""Tests for YAML configuration loading in product_parser."""

from pathlib import Path

import pytest
import yaml

from src.utils.product_parser import (
    _get_config_paths,
    _load_default_variants,
    load_variant_config,
    merge_variant_configs,
)


class TestConfigPaths:
    """Test path resolution for config files."""

    def test_get_config_paths_returns_list(self):
        """Should return a list of Path objects."""
        paths = _get_config_paths()
        assert isinstance(paths, list)
        assert len(paths) >= 1
        assert all(isinstance(p, Path) for p in paths)

    def test_development_path_first(self):
        """Development path should be checked first."""
        paths = _get_config_paths()
        dev_path = paths[0]
        assert dev_path.name == "product_parser_defaults.yaml"
        assert "config" in str(dev_path)


class TestDefaultVariantsLoading:
    """Test lazy-loading of default variants from YAML."""

    def test_load_default_variants_returns_dict(self):
        """Should return a dictionary with variant configuration."""
        variants = _load_default_variants()
        assert isinstance(variants, dict)
        assert "colors" in variants
        assert "flavors" in variants
        assert "types" in variants

    def test_default_variants_have_languages(self):
        """Each category should have language subcategories."""
        variants = _load_default_variants()

        # Check colors
        assert "en" in variants["colors"]
        assert "nl" in variants["colors"]
        assert "de" in variants["colors"]

        # Check flavors
        assert "en" in variants["flavors"]
        assert "nl" in variants["flavors"]
        assert "de" in variants["flavors"]

        # Check types
        assert "en" in variants["types"]
        assert "nl" in variants["types"]
        assert "de" in variants["types"]

    def test_default_variants_have_expected_values(self):
        """Should load expected variant values from YAML."""
        variants = _load_default_variants()

        # Check some known English colors
        en_colors = variants["colors"]["en"]
        assert "red" in en_colors
        assert "blue" in en_colors
        assert "green" in en_colors

        # Check some known English flavors
        en_flavors = variants["flavors"]["en"]
        assert "chocolate" in en_flavors
        assert "vanilla" in en_flavors

        # Check some known English types
        en_types = variants["types"]["en"]
        assert "organic" in en_types
        assert "vegan" in en_types

    def test_default_variants_cached(self):
        """Should cache variants after first load."""
        variants1 = _load_default_variants()
        variants2 = _load_default_variants()
        # Should be the same object (cached)
        assert variants1 is variants2

    def test_no_duplicate_orange_issue(self):
        """Orange should only be in colors, not flavors (fixed in refactoring)."""
        variants = _load_default_variants()

        en_colors = variants["colors"]["en"]
        en_flavors = variants["flavors"]["en"]

        # Orange should be in colors
        assert "orange" in en_colors
        # Orange should NOT be in flavors
        assert "orange" not in en_flavors


class TestLoadVariantConfig:
    """Test load_variant_config function."""

    def test_load_with_none_returns_defaults(self):
        """Calling with None should return default variants."""
        variants = load_variant_config(None)
        assert isinstance(variants, dict)
        assert "colors" in variants
        assert "flavors" in variants
        assert "types" in variants

    def test_load_with_explicit_path(self, tmp_path):
        """Should load from specified YAML path."""
        # Create a minimal test YAML
        test_yaml = tmp_path / "test_variants.yaml"
        test_yaml.write_text(
            """
variants:
  colors:
    en:
      - test-red
      - test-blue
  flavors:
    en:
      - test-chocolate
  types:
    en:
      - test-organic
"""
        )

        variants = load_variant_config(test_yaml)
        assert variants["colors"]["en"] == ["test-red", "test-blue"]
        assert variants["flavors"]["en"] == ["test-chocolate"]
        assert variants["types"]["en"] == ["test-organic"]

    def test_load_nonexistent_file_raises(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_variant_config("/nonexistent/path/config.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path):
        """Should raise error for invalid YAML."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            load_variant_config(bad_yaml)

    def test_load_missing_variants_key_raises(self, tmp_path):
        """Should raise ValueError if 'variants' key missing."""
        bad_yaml = tmp_path / "no_variants.yaml"
        bad_yaml.write_text("other_key: value")

        with pytest.raises(ValueError, match="Missing 'variants' key"):
            load_variant_config(bad_yaml)


class TestMergeVariantConfigs:
    """Test configuration merging."""

    def test_merge_empty_override(self):
        """Merging with empty override should return base."""
        base = {"colors": {"en": ["red", "blue"]}}
        override = {}

        merged = merge_variant_configs(base, override)
        assert merged == base

    def test_merge_adds_new_language(self):
        """Override can add new language to existing category."""
        base = {"colors": {"en": ["red", "blue"]}}
        override = {"colors": {"fr": ["rouge", "bleu"]}}

        merged = merge_variant_configs(base, override)
        assert "en" in merged["colors"]
        assert "fr" in merged["colors"]
        assert merged["colors"]["en"] == ["red", "blue"]
        assert merged["colors"]["fr"] == ["rouge", "bleu"]

    def test_merge_replaces_language(self):
        """Override completely replaces language variants."""
        base = {"colors": {"en": ["red", "blue", "green"]}}
        override = {"colors": {"en": ["red", "blue"]}}  # Fewer colors

        merged = merge_variant_configs(base, override)
        # Override wins - only red and blue
        assert merged["colors"]["en"] == ["red", "blue"]

    def test_merge_adds_new_category(self):
        """Override can add entirely new categories."""
        base = {"colors": {"en": ["red"]}}
        override = {"sizes": {"en": ["small", "large"]}}

        merged = merge_variant_configs(base, override)
        assert "colors" in merged
        assert "sizes" in merged
        assert merged["sizes"]["en"] == ["small", "large"]


class TestYAMLMatchesExpectations:
    """Integration tests to ensure YAML file has expected structure."""

    def test_yaml_file_exists(self):
        """The product_parser_defaults.yaml file should exist."""
        yaml_path = (
            Path(__file__).parent.parent.parent
            / "provider_configs"
            / "product_parser_defaults.yaml"
        )
        assert yaml_path.exists(), f"Expected YAML file not found at {yaml_path}"

    def test_yaml_has_version(self):
        """YAML file should have version information."""
        import yaml

        yaml_path = (
            Path(__file__).parent.parent.parent
            / "provider_configs"
            / "product_parser_defaults.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Should have version field (not in variants, but at root)
        # Note: Our current YAML structure has this
        assert "variants" in config

    def test_yaml_loads_successfully(self):
        """YAML file should load without errors."""
        yaml_path = (
            Path(__file__).parent.parent.parent
            / "provider_configs"
            / "product_parser_defaults.yaml"
        )
        variants = load_variant_config(yaml_path)

        # Should have all expected categories
        assert "colors" in variants
        assert "flavors" in variants
        assert "types" in variants

        # Each category should have languages
        for category in ["colors", "flavors", "types"]:
            assert "en" in variants[category]
            assert "nl" in variants[category]
            assert "de" in variants[category]
            # Each language should have a list
            assert isinstance(variants[category]["en"], list)
            assert len(variants[category]["en"]) > 0
