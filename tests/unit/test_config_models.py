from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError
import pytest

from src.config.models import (
    AppConfig,
    BrowserType,
    CLIConfig,
    DatabaseConfig,
    ProviderConfig,
    ScrapingConfig,
    WaitStrategy,
)


class TestDatabaseConfig:
    """Test DatabaseConfig model validation and field behavior."""

    def test_default_values(self):
        """Test default field values are set correctly."""
        config = DatabaseConfig()

        assert config.url == ""
        assert config.export_to_parquet is True
        assert config.parquet_path == "./data/snapshots.parquet"

    def test_empty_url_is_valid(self):
        """Test that empty URL is valid (uses platform defaults)."""
        config = DatabaseConfig(url="")
        assert config.url == ""

        config = DatabaseConfig(url="   ")
        assert config.url == ""

    def test_database_url_formats(self):
        """Test various database URL formats are accepted."""
        config = DatabaseConfig(url="./test.duckdb")
        assert config.url == "./test.duckdb"

        config = DatabaseConfig(url="postgresql://user:pass@localhost/db")
        assert config.url == "postgresql://user:pass@localhost/db"

        config = DatabaseConfig(url="sqlite:///./test.db")
        assert config.url == "sqlite:///./test.db"

    def test_existing_file_path_normalized(self):
        """Test that existing file paths are normalized to absolute paths."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.duckdb"
            test_file.touch()

            config = DatabaseConfig(url=str(test_file))
            assert Path(config.url).is_absolute()
            assert Path(config.url).exists()

    def test_new_file_path_preserved(self):
        """Test that new (non-existent) file paths are preserved."""
        config = DatabaseConfig(url="./new_database.duckdb")
        assert config.url == "./new_database.duckdb"

    def test_parquet_path_creates_parent_directory(self):
        """Test that parent directory is created for parquet_path."""
        with TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "nested" / "dir" / "data.parquet"

            config = DatabaseConfig(parquet_path=str(parquet_path))

            assert parquet_path.parent.exists()
            assert config.parquet_path == str(parquet_path)

    def test_export_to_parquet_boolean(self):
        """Test export_to_parquet accepts boolean values."""
        config = DatabaseConfig(export_to_parquet=True)
        assert config.export_to_parquet is True

        config = DatabaseConfig(export_to_parquet=False)
        assert config.export_to_parquet is False


class TestAppConfig:
    """Test AppConfig model validation and integration."""

    def test_minimal_valid_config(self):
        """Test minimal valid configuration with only database section."""
        config_data = {"database": {"url": "", "export_to_parquet": True}}

        config = AppConfig(**config_data)

        assert config.database.url == ""
        assert config.database.export_to_parquet is True

    def test_database_config_required(self):
        """Test that database config is required."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig()

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("database",) for error in errors)

    def test_full_config_structure(self):
        """Test complete configuration with all sections."""
        config_data = {
            "database": {
                "url": "./test.duckdb",
                "export_to_parquet": True,
                "parquet_path": "./data/snapshots.parquet",
            },
            "cli": {"max_parallel_urls": 25},
            "scraping": {"headless": True, "browser_type": "firefox"},
            "providers": {
                "store_a": {
                    "name": "store_a",
                    "country": "NL",
                    "base_url": "https://www.store-a.example",
                }
            },
            "product_groups": [
                {
                    "name": "Test Group",
                    "pages": [{"url": "https://example.com", "provider": "test"}],
                }
            ],
        }

        config = AppConfig(**config_data)

        assert config.database.url == "./test.duckdb"
        assert isinstance(config.database, DatabaseConfig)

        assert isinstance(config.scraping, ScrapingConfig)
        assert config.scraping.headless is True
        assert config.scraping.browser_type == BrowserType.FIREFOX

        assert isinstance(config.providers, dict)
        assert len(config.providers) == 1
        assert isinstance(config.providers["store_a"], ProviderConfig)
        assert config.providers["store_a"].name == "store_a"

        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 25

        assert len(config.product_groups) == 1

    def test_backward_compatible_get_method(self):
        """Test that get() method provides dict-like access for backward compatibility."""
        config_data = {
            "database": {"url": "./test.duckdb"},
            "cli": {"max_parallel_urls": 25},
        }

        config = AppConfig(**config_data)

        assert config.get("database") == config.database
        assert config.get("cli") == config.cli
        assert config.get("nonexistent") is None
        assert config.get("nonexistent", "default") == "default"

    def test_minimal_config_with_defaults(self):
        """Test that minimal config works with smart defaults."""
        config_data = {"database": {"url": ""}}

        config = AppConfig(**config_data)

        assert config.scraping.headless is True
        assert config.providers == {}
        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 25
        assert config.product_groups == []

    def test_validation_on_assignment(self):
        """Test that validation occurs when assigning to fields."""
        config = AppConfig(database={"url": ""})

        config.database = DatabaseConfig(url="./new.duckdb")
        assert config.database.url == "./new.duckdb"

        with pytest.raises(ValidationError):
            config.database = "not a DatabaseConfig object"  # type: ignore


class TestBrowserType:
    """Test BrowserType enum validation."""

    def test_valid_browser_types(self):
        """Test that valid browser types are accepted."""
        assert BrowserType.CHROMIUM.value == "chromium"
        assert BrowserType.FIREFOX.value == "firefox"
        assert BrowserType.WEBKIT.value == "webkit"

    def test_browser_type_in_config(self):
        """Test browser type validation in ScrapingConfig."""
        config = ScrapingConfig(browser_type=BrowserType.FIREFOX)
        assert config.browser_type == BrowserType.FIREFOX

        config = ScrapingConfig(browser_type="chromium")
        assert config.browser_type == BrowserType.CHROMIUM


class TestScrapingConfig:
    """Test ScrapingConfig model validation and defaults."""

    def test_default_values(self):
        """Test default scraping configuration values."""
        config = ScrapingConfig()

        assert config.user_agent_rotation is True
        assert config.request_delay_seconds == 2.0
        assert config.max_retries == 3
        assert config.timeout_seconds == 30
        assert config.strip_query_params is True

        assert config.use_playwright is True
        assert config.headless is True
        assert config.browser_type == BrowserType.CHROMIUM
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.locale == "nl-NL"
        assert config.timezone == "Europe/Amsterdam"

        assert config.save_screenshots is False
        assert config.screenshots_dir == "logs/screenshots"

    def test_custom_browser_settings(self):
        """Test custom browser configuration."""
        config = ScrapingConfig(
            headless=False,
            browser_type=BrowserType.FIREFOX,
            viewport_width=1366,
            viewport_height=768,
            locale="en-US",
            timezone="America/New_York",
        )

        assert config.headless is False
        assert config.browser_type == BrowserType.FIREFOX
        assert config.viewport_width == 1366
        assert config.viewport_height == 768
        assert config.locale == "en-US"
        assert config.timezone == "America/New_York"

    def test_request_delay_validation(self):
        """Test that request_delay_seconds must be non-negative."""
        ScrapingConfig(request_delay_seconds=0.0)
        ScrapingConfig(request_delay_seconds=5.5)

        with pytest.raises(ValidationError):
            ScrapingConfig(request_delay_seconds=-1.0)

    def test_timeout_validation(self):
        """Test that timeout_seconds must be at least 1."""
        ScrapingConfig(timeout_seconds=1)
        ScrapingConfig(timeout_seconds=60)

        with pytest.raises(ValidationError):
            ScrapingConfig(timeout_seconds=0)

    def test_viewport_size_validation(self):
        """Test viewport width/height validation."""
        ScrapingConfig(viewport_width=320, viewport_height=240)  # Min
        ScrapingConfig(viewport_width=7680, viewport_height=4320)  # Max

        with pytest.raises(ValidationError):
            ScrapingConfig(viewport_width=100)

        with pytest.raises(ValidationError):
            ScrapingConfig(viewport_height=10000)

    def test_screenshots_directory_created(self):
        """Test that screenshots directory is created."""
        with TemporaryDirectory() as tmpdir:
            screenshots_path = Path(tmpdir) / "test_screenshots"

            config = ScrapingConfig(screenshots_dir=str(screenshots_path))

            assert screenshots_path.exists()
            assert config.screenshots_dir == str(screenshots_path)


class TestAppConfigWithScraping:
    """Test AppConfig with ScrapingConfig integration (Phase 2)."""

    def test_scraping_config_defaults(self):
        """Test that scraping config has defaults when not provided."""
        config = AppConfig(database={"url": ""})

        assert isinstance(config.scraping, ScrapingConfig)
        assert config.scraping.headless is True
        assert config.scraping.browser_type == BrowserType.CHROMIUM

    def test_custom_scraping_config(self):
        """Test custom scraping configuration in AppConfig."""
        config_data = {
            "database": {"url": ""},
            "scraping": {
                "headless": False,
                "browser_type": "firefox",
                "viewport_width": 1280,
                "viewport_height": 720,
                "save_screenshots": True,
            },
        }

        config = AppConfig(**config_data)

        assert config.scraping.headless is False
        assert config.scraping.browser_type == BrowserType.FIREFOX
        assert config.scraping.viewport_width == 1280
        assert config.scraping.save_screenshots is True

    def test_full_config_with_typed_sections(self):
        """Test complete config with Phase 1 and Phase 2 typed sections."""
        config_data = {
            "database": {
                "url": "./test.duckdb",
                "export_to_parquet": True,
            },
            "scraping": {
                "headless": False,
                "browser_type": "webkit",
                "request_delay_seconds": 3.5,
            },
            "cli": {"max_parallel_urls": 50},
            "providers": {},
        }

        config = AppConfig(**config_data)

        assert isinstance(config.database, DatabaseConfig)
        assert config.database.url == "./test.duckdb"

        assert isinstance(config.scraping, ScrapingConfig)
        assert config.scraping.headless is False
        assert config.scraping.browser_type == BrowserType.WEBKIT
        assert config.scraping.request_delay_seconds == 3.5

        assert isinstance(config.providers, dict)
        assert len(config.providers) == 0

        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 50


class TestWaitStrategy:
    """Test WaitStrategy enum validation."""

    def test_valid_wait_strategies(self):
        """Test that valid wait strategies are accepted."""
        assert WaitStrategy.COMMIT.value == "commit"
        assert WaitStrategy.DOMCONTENTLOADED.value == "domcontentloaded"
        assert WaitStrategy.LOAD.value == "load"
        assert WaitStrategy.NETWORKIDLE.value == "networkidle"

    def test_all_playwright_values_covered(self):
        """Test that all Playwright wait_until values are in the enum."""
        # Playwright supports: commit, domcontentloaded, load, networkidle
        expected_values = {"commit", "domcontentloaded", "load", "networkidle"}
        actual_values = {strategy.value for strategy in WaitStrategy}
        assert actual_values == expected_values


class TestProviderConfig:
    """Test ProviderConfig model validation."""

    def test_minimal_provider_config(self):
        """Test minimal valid provider configuration."""
        config = ProviderConfig(
            name="test",
            country="NL",
            base_url="https://www.example.com",
        )

        assert config.name == "test"
        assert config.country == "NL"
        assert config.base_url == "https://www.example.com"
        assert config.wait_strategy == WaitStrategy.DOMCONTENTLOADED
        assert config.wait_delay == 0
        assert config.custom_class is None
        assert config.extraction == {}
        assert config.transformations == {}

    def test_full_provider_config(self):
        """Test complete provider configuration with all fields."""
        config = ProviderConfig(
            name="store_a",
            country="nl",
            base_url="https://www.store-a.example/",
            wait_strategy=WaitStrategy.NETWORKIDLE,
            wait_delay=2,
            custom_class="StoreAProvider",
            extraction={
                "priority": ["json-ld"],
                "json_ld": {"default_availability_when_missing": True},
            },
            transformations={"category": {"type": "split", "delimiter": ","}},
        )

        assert config.name == "store_a"
        assert config.country == "NL"
        assert config.base_url == "https://www.store-a.example"
        assert config.wait_strategy == WaitStrategy.NETWORKIDLE
        assert config.wait_delay == 2
        assert config.custom_class == "StoreAProvider"
        assert config.extraction["priority"] == ["json-ld"]
        assert config.transformations["category"]["type"] == "split"

    def test_country_code_validation(self):
        """Test country code is validated and uppercased."""
        config = ProviderConfig(name="test", country="us", base_url="https://example.com")
        assert config.country == "US"

        with pytest.raises(ValidationError):
            ProviderConfig(name="test", country="U", base_url="https://example.com")

        with pytest.raises(ValidationError):
            ProviderConfig(name="test", country="USA", base_url="https://example.com")

    def test_base_url_validation(self):
        """Test base URL validation."""
        ProviderConfig(name="test", country="NL", base_url="https://www.example.com")
        ProviderConfig(name="test", country="NL", base_url="http://localhost:3000")

        with pytest.raises(ValidationError):
            ProviderConfig(name="test", country="NL", base_url="www.example.com")

        with pytest.raises(ValidationError):
            ProviderConfig(name="test", country="NL", base_url="ftp://example.com")

    def test_wait_delay_validation(self):
        """Test wait_delay must be between 0-30 seconds."""
        ProviderConfig(name="test", country="NL", base_url="https://example.com", wait_delay=0)
        ProviderConfig(name="test", country="NL", base_url="https://example.com", wait_delay=30)

        with pytest.raises(ValidationError):
            ProviderConfig(name="test", country="NL", base_url="https://example.com", wait_delay=31)

        with pytest.raises(ValidationError):
            ProviderConfig(name="test", country="NL", base_url="https://example.com", wait_delay=-1)

    def test_wait_strategy_enum(self):
        """Test wait_strategy accepts WaitStrategy enum."""
        config = ProviderConfig(
            name="test",
            country="NL",
            base_url="https://example.com",
            wait_strategy=WaitStrategy.LOAD,
        )
        assert config.wait_strategy == WaitStrategy.LOAD

        # String values should work (Pydantic coercion)
        config = ProviderConfig(
            name="test",
            country="NL",
            base_url="https://example.com",
            wait_strategy="networkidle",
        )
        assert config.wait_strategy == WaitStrategy.NETWORKIDLE


class TestAppConfigWithProviders:
    """Test AppConfig with ProviderConfig integration (Phase 3)."""

    def test_providers_as_typed_dict(self):
        """Test providers are validated as ProviderConfig objects."""
        config_data = {
            "database": {"url": ""},
            "providers": {
                "store_a": {
                    "name": "store_a",
                    "country": "NL",
                    "base_url": "https://www.store-a.example",
                },
                "store_c": {
                    "name": "store_c",
                    "country": "nl",
                    "base_url": "https://www.store-c.example/",
                    "wait_strategy": "networkidle",
                },
            },
        }

        config = AppConfig(**config_data)

        assert isinstance(config.providers, dict)
        assert len(config.providers) == 2
        assert isinstance(config.providers["store_a"], ProviderConfig)
        assert isinstance(config.providers["store_c"], ProviderConfig)

        assert config.providers["store_a"].name == "store_a"
        assert config.providers["store_a"].country == "NL"
        assert config.providers["store_c"].country == "NL"
        assert config.providers["store_c"].base_url == "https://www.store-c.example"

    def test_invalid_provider_raises_validation_error(self):
        """Test that invalid provider config raises ValidationError."""
        config_data = {
            "database": {"url": ""},
            "providers": {
                "invalid": {
                    "name": "test",
                    # Missing required fields: country, base_url
                }
            },
        }

        with pytest.raises(ValidationError):
            AppConfig(**config_data)

    def test_full_config_all_phases(self):
        """Test complete config with all phases (1, 2, 3) typed."""
        config_data = {
            "database": {"url": "./test.duckdb"},
            "scraping": {"headless": False, "browser_type": "firefox"},
            "providers": {
                "store_a": {
                    "name": "store_a",
                    "country": "NL",
                    "base_url": "https://www.store-a.example",
                    "extraction": {"priority": ["json-ld"]},
                }
            },
            "cli": {"max_parallel_urls": 25},
        }

        config = AppConfig(**config_data)

        assert isinstance(config.database, DatabaseConfig)

        assert isinstance(config.scraping, ScrapingConfig)
        assert config.scraping.headless is False

        assert isinstance(config.providers["store_a"], ProviderConfig)
        assert config.providers["store_a"].extraction["priority"] == ["json-ld"]

        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 25


class TestCLIConfig:
    """Test CLIConfig model validation and field behavior."""

    def test_default_values(self):
        """Test that CLI config has sensible defaults."""
        config = CLIConfig()

        assert config.max_parallel_urls == 25

    def test_custom_max_parallel_urls(self):
        """Test custom max_parallel_urls value."""
        config = CLIConfig(max_parallel_urls=50)

        assert config.max_parallel_urls == 50

    def test_max_parallel_urls_validation_minimum(self):
        """Test that max_parallel_urls must be at least 1."""
        with pytest.raises(ValidationError) as exc_info:
            CLIConfig(max_parallel_urls=0)

        assert "greater than or equal to 1" in str(exc_info.value).lower()

    def test_max_parallel_urls_validation_maximum(self):
        """Test that max_parallel_urls cannot exceed 100."""
        with pytest.raises(ValidationError) as exc_info:
            CLIConfig(max_parallel_urls=101)

        assert "less than or equal to 100" in str(exc_info.value).lower()

    def test_max_parallel_urls_edge_cases(self):
        """Test edge cases for max_parallel_urls (1 and 100)."""
        config_min = CLIConfig(max_parallel_urls=1)
        config_max = CLIConfig(max_parallel_urls=100)

        assert config_min.max_parallel_urls == 1
        assert config_max.max_parallel_urls == 100

    def test_no_extra_fields_allowed(self):
        """Test that extra fields are not allowed in CLIConfig."""
        with pytest.raises(ValidationError) as exc_info:
            CLIConfig(max_parallel_urls=25, unknown_field="value")

        assert "extra inputs are not permitted" in str(exc_info.value).lower()


class TestAppConfigWithCLI:
    """Test AppConfig integration with CLIConfig."""

    def test_cli_config_defaults(self):
        """Test that CLI config has defaults when not provided."""
        config = AppConfig(database={"url": ""})

        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 25

    def test_custom_cli_config(self):
        """Test custom CLI configuration."""
        config_data = {"database": {"url": ""}, "cli": {"max_parallel_urls": 10}}

        config = AppConfig(**config_data)

        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 10

    def test_full_config_all_phases_complete(self):
        """Test complete config with all phases (1, 2, 3, 4) typed."""
        config_data = {
            "database": {"url": "./test.duckdb"},
            "scraping": {"headless": False, "browser_type": "firefox"},
            "providers": {
                "store_a": {
                    "name": "store_a",
                    "country": "NL",
                    "base_url": "https://www.store-a.example",
                    "extraction": {"priority": ["json-ld"]},
                }
            },
            "cli": {"max_parallel_urls": 50},
        }

        config = AppConfig(**config_data)

        assert isinstance(config.database, DatabaseConfig)

        assert isinstance(config.scraping, ScrapingConfig)
        assert config.scraping.headless is False

        assert isinstance(config.providers["store_a"], ProviderConfig)

        assert isinstance(config.cli, CLIConfig)
        assert config.cli.max_parallel_urls == 50
