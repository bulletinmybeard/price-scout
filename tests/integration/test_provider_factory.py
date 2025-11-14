from collections.abc import Generator
from pathlib import Path
import tempfile

from pydantic import ValidationError
import pytest
import yaml

from src.config.models import ProviderConfig
import src.providers.provider_factory as pf_module
from src.providers.provider_factory import ProviderFactory, get_factory


@pytest.fixture
def temp_config_dir() -> Generator[tuple[Path, Path], None, None]:
    """Create temporary directory with config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        config_path = tmpdir_path / "config.yaml"
        config_data = {
            "database": {
                "path": ":memory:",
                "export_to_parquet": False,
            },
            "scraping": {
                "headless": True,
                "timeout": 30000,
            },
            "providers": {
                "test_provider_1": {
                    "name": "test_provider_1",
                    "country": "NL",
                    "base_url": "https://test1.com",
                },
                "test_provider_2": {
                    "name": "test_provider_2",
                    "country": "NL",
                    "base_url": "https://test2.com",
                },
            },
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        yield tmpdir_path, config_path


class TestProviderFactoryInit:
    """Tests for ProviderFactory initialization."""

    def test_init_with_config_path(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test initialization with explicit config path."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        assert factory.config_loader is not None
        assert factory.full_config is not None
        assert factory.config is not None

    def test_init_loads_providers_from_config_yaml(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that providers are loaded from config.yaml as ProviderConfig models."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        assert "test_provider_1" in factory.config
        assert "test_provider_2" in factory.config
        assert isinstance(factory.config["test_provider_1"], ProviderConfig)
        assert factory.config["test_provider_1"].base_url == "https://test1.com"


class TestLoadConfig:
    """Tests for _load_config method."""

    def test_load_config_returns_tuple(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that _load_config returns (full_config, providers_dict)."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        full_config, providers = factory._load_config()

        assert isinstance(full_config, dict)
        assert isinstance(providers, dict)
        assert "database" in full_config
        assert "scraping" in full_config

    def test_full_config_contains_all_sections(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that full_config contains all config sections."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        assert "database" in factory.full_config
        assert "scraping" in factory.full_config
        assert "providers" in factory.full_config

    def test_config_contains_only_providers(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that config dict contains only providers."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        assert "test_provider_1" in factory.config
        assert "test_provider_2" in factory.config

        assert "database" not in factory.config
        assert "scraping" not in factory.config


class TestGetProvider:
    """Tests for get_provider method."""

    def test_get_provider_returns_configurable_provider(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that get_provider returns ConfigurableProvider for config-based providers."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        provider = factory.get_provider("test_provider_1", headless=True)

        from src.providers.configurable_provider import ConfigurableProvider

        assert isinstance(provider, ConfigurableProvider)

    def test_get_provider_with_headless_flag(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that headless flag is passed to provider."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        provider_headless = factory.get_provider("test_provider_1", headless=True)
        provider_headed = factory.get_provider("test_provider_1", headless=False)

        assert provider_headless.headless is True
        assert provider_headed.headless is False

    def test_get_provider_not_found_raises_error(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that getting non-existent provider raises ValueError."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        with pytest.raises(ValueError) as exc_info:
            factory.get_provider("nonexistent_provider")

        assert "Provider 'nonexistent_provider' not found" in str(exc_info.value)
        assert "Available providers:" in str(exc_info.value)

    def test_get_provider_error_shows_available_providers(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that error message lists available providers."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        with pytest.raises(ValueError) as exc_info:
            factory.get_provider("nonexistent")

        error_msg = str(exc_info.value)
        assert "test_provider_1" in error_msg
        assert "test_provider_2" in error_msg


class TestListProviders:
    """Tests for list_providers method."""

    def test_list_providers_returns_sorted_list(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that list_providers returns sorted list of provider names."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        providers = factory.list_providers()

        assert isinstance(providers, list)
        assert "test_provider_1" in providers
        assert "test_provider_2" in providers
        assert providers == sorted(providers)

    def test_list_providers_returns_all_config_providers(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that list_providers returns all providers from config.yaml."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        providers = factory.list_providers()

        assert len(providers) >= 2
        assert "test_provider_1" in providers
        assert "test_provider_2" in providers


class TestReloadConfig:
    """Tests for reload_config method."""

    def test_reload_config_refreshes_providers(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that reload_config reloads provider configurations."""
        _tmpdir_path, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        initial_providers = factory.list_providers()
        assert "test_provider_1" in initial_providers

        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        config_data["providers"]["test_provider_3"] = {
            "name": "test_provider_3",
            "country": "NL",
            "base_url": "https://test3.com",
        }

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory.reload_config()

        updated_providers = factory.list_providers()
        assert "test_provider_3" in updated_providers

    def test_reload_config_updates_full_config(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that reload_config updates both config and full_config."""
        _tmpdir_path, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        original_timeout = factory.full_config["scraping"]["timeout"]
        assert original_timeout == 30000

        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        config_data["scraping"]["timeout"] = 60000

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory.reload_config()

        assert factory.full_config["scraping"]["timeout"] == 60000


class TestGetFactory:
    """Tests for get_factory global factory function."""

    def test_get_factory_returns_singleton(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that get_factory returns same instance."""
        _, config_path = temp_config_dir

        pf_module._factory_instance = None

        factory1 = get_factory(config_path=str(config_path))
        factory2 = get_factory()

        assert factory1 is factory2

    def test_get_factory_with_new_config_path_creates_new_instance(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that providing new config_path creates new instance."""
        tmpdir_path, config_path = temp_config_dir

        config_path_2 = tmpdir_path / "config2.yaml"
        config_data_2 = {
            "database": {"path": ":memory:"},
            "providers": {
                "other_provider": {
                    "name": "other_provider",
                    "country": "US",  # Required field
                    "base_url": "https://other.com",
                }
            },
        }
        with open(config_path_2, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data_2, f)

        import src.providers.provider_factory as pf_module

        pf_module._factory_instance = None

        factory1 = get_factory(config_path=str(config_path))
        factory2 = get_factory(config_path=str(config_path_2))

        assert factory1 is not factory2
        assert "test_provider_1" in factory1.list_providers()
        assert "other_provider" in factory2.list_providers()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_providers_section(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test handling of config with no providers."""
        tmpdir_path, _ = temp_config_dir

        empty_config = tmpdir_path / "empty_config.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "scraping": {"headless": True},
        }
        with open(empty_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory = ProviderFactory(config_path=str(empty_config))
        assert isinstance(factory.list_providers(), list)

    def test_provider_config_structure(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that provider config preserves all fields as Pydantic model."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        provider_config = factory.config["test_provider_1"]

        # Now a Pydantic model, not dict
        assert isinstance(provider_config, ProviderConfig)
        assert provider_config.name == "test_provider_1"
        assert provider_config.country == "NL"
        assert provider_config.base_url == "https://test1.com"

    def test_multiple_provider_retrieval(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test retrieving multiple different providers."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        provider1 = factory.get_provider("test_provider_1")
        provider2 = factory.get_provider("test_provider_2")

        assert provider1 is not provider2
        assert provider1.name == "test_provider_1"
        assert provider2.name == "test_provider_2"

    def test_provider_with_minimal_required_fields(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test provider with minimal config (only required fields: name, country, base_url)."""
        tmpdir_path, _ = temp_config_dir

        minimal_config = tmpdir_path / "minimal_config.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "minimal_provider": {
                    "name": "minimal_provider",
                    "country": "NL",  # Required
                    "base_url": "https://minimal.com",  # Required
                    # Optional fields omitted (wait_strategy, wait_delay, custom_class, etc.)
                }
            },
        }
        with open(minimal_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory = ProviderFactory(config_path=str(minimal_config))

        assert "minimal_provider" in factory.config

        provider = factory.get_provider("minimal_provider")
        assert provider is not None

    def test_config_loader_integration(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that factory properly integrates with ConfigLoader."""
        _, config_path = temp_config_dir
        factory = ProviderFactory(config_path=str(config_path))

        assert factory.config_loader is not None

        assert "database" in factory.full_config
        assert "scraping" in factory.full_config
        assert "providers" in factory.full_config


class TestPydanticValidation:
    """Tests for Pydantic validation of provider configs."""

    def test_valid_provider_config_loads(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that valid provider config is validated and loaded correctly."""
        tmpdir_path, _ = temp_config_dir

        valid_config = tmpdir_path / "valid_config.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "valid_provider": {
                    "name": "valid_provider",
                    "country": "NL",
                    "base_url": "https://example.com",
                    "wait_strategy": "domcontentloaded",
                    "wait_delay": 2,
                }
            },
        }
        with open(valid_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory = ProviderFactory(config_path=str(valid_config))

        assert "valid_provider" in factory.config
        provider_config = factory.config["valid_provider"]
        assert isinstance(provider_config, ProviderConfig)
        assert provider_config.name == "valid_provider"
        assert provider_config.country == "NL"
        assert provider_config.base_url == "https://example.com"

    def test_invalid_wait_strategy_raises_validation_error(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that invalid wait_strategy value raises ValidationError."""
        tmpdir_path, _ = temp_config_dir

        invalid_config = tmpdir_path / "invalid_wait_strategy.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "invalid_provider": {
                    "name": "invalid_provider",
                    "country": "NL",
                    "base_url": "https://example.com",
                    "wait_strategy": "invalid_strategy",  # Not a valid WaitStrategy
                }
            },
        }
        with open(invalid_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        with pytest.raises(ValidationError) as exc_info:
            ProviderFactory(config_path=str(invalid_config))

        assert "wait_strategy" in str(exc_info.value)

    def test_wait_delay_out_of_bounds_raises_validation_error(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that wait_delay outside valid range raises ValidationError."""
        tmpdir_path, _ = temp_config_dir

        invalid_config = tmpdir_path / "invalid_wait_delay.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "invalid_provider": {
                    "name": "invalid_provider",
                    "country": "NL",
                    "base_url": "https://example.com",
                    "wait_delay": 100,  # Max is 30
                }
            },
        }
        with open(invalid_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        with pytest.raises(ValidationError) as exc_info:
            ProviderFactory(config_path=str(invalid_config))

        assert "wait_delay" in str(exc_info.value)

    def test_negative_wait_delay_raises_validation_error(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that negative wait_delay raises ValidationError."""
        tmpdir_path, _ = temp_config_dir

        invalid_config = tmpdir_path / "negative_wait_delay.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "invalid_provider": {
                    "name": "invalid_provider",
                    "country": "NL",
                    "base_url": "https://example.com",
                    "wait_delay": -1,  # Min is 0
                }
            },
        }
        with open(invalid_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        with pytest.raises(ValidationError) as exc_info:
            ProviderFactory(config_path=str(invalid_config))

        assert "wait_delay" in str(exc_info.value)

    def test_missing_required_name_field_raises_validation_error(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that missing required 'name' field raises ValidationError."""
        tmpdir_path, _ = temp_config_dir

        invalid_config = tmpdir_path / "missing_name.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "invalid_provider": {
                    # Missing 'name' field
                    "country": "NL",
                    "base_url": "https://example.com",
                }
            },
        }
        with open(invalid_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        with pytest.raises(ValidationError) as exc_info:
            ProviderFactory(config_path=str(invalid_config))

        assert "name" in str(exc_info.value)

    def test_invalid_base_url_format_raises_validation_error(
        self, temp_config_dir: tuple[Path, Path]
    ) -> None:
        """Test that base_url without http(s):// raises ValidationError."""
        tmpdir_path, _ = temp_config_dir

        invalid_config = tmpdir_path / "invalid_base_url.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "invalid_provider": {
                    "name": "invalid_provider",
                    "country": "NL",
                    "base_url": "example.com",  # Missing http://
                }
            },
        }
        with open(invalid_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        with pytest.raises(ValidationError) as exc_info:
            ProviderFactory(config_path=str(invalid_config))

        assert "base_url" in str(exc_info.value)

    def test_country_code_normalization(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that country codes are normalized to uppercase."""
        tmpdir_path, _ = temp_config_dir

        lowercase_config = tmpdir_path / "lowercase_country.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "test_provider": {
                    "name": "test_provider",
                    "country": "nl",  # Lowercase
                    "base_url": "https://example.com",
                }
            },
        }
        with open(lowercase_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory = ProviderFactory(config_path=str(lowercase_config))

        provider_config = factory.config["test_provider"]
        assert provider_config.country == "NL"  # Should be uppercase

    def test_base_url_trailing_slash_removed(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that trailing slash is removed from base_url."""
        tmpdir_path, _ = temp_config_dir

        trailing_slash_config = tmpdir_path / "trailing_slash.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "test_provider": {
                    "name": "test_provider",
                    "country": "NL",
                    "base_url": "https://example.com/",  # With trailing slash
                }
            },
        }
        with open(trailing_slash_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory = ProviderFactory(config_path=str(trailing_slash_config))

        provider_config = factory.config["test_provider"]
        assert provider_config.base_url == "https://example.com"  # No trailing slash

    def test_default_values_applied(self, temp_config_dir: tuple[Path, Path]) -> None:
        """Test that Pydantic applies default values for optional fields."""
        tmpdir_path, _ = temp_config_dir

        minimal_config = tmpdir_path / "minimal_with_defaults.yaml"
        config_data = {
            "database": {"path": ":memory:"},
            "providers": {
                "minimal_provider": {
                    "name": "minimal_provider",
                    "country": "NL",
                    "base_url": "https://example.com",
                    # Omit wait_strategy, wait_delay, custom_class
                }
            },
        }
        with open(minimal_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        factory = ProviderFactory(config_path=str(minimal_config))

        provider_config = factory.config["minimal_provider"]
        # Check defaults are applied
        assert provider_config.wait_strategy.value == "domcontentloaded"  # Default
        assert provider_config.wait_delay == 0  # Default
        assert provider_config.custom_class is None  # Default
