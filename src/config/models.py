from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BrowserType(str, Enum):
    """Supported browser types for Playwright automation."""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class ScrapingConfig(BaseModel):
    """Web scraping configuration with Playwright browser automation settings."""

    # Request settings
    user_agent_rotation: bool = Field(
        default=True,
        description="Rotate user agents to avoid detection",
    )
    request_delay_seconds: float = Field(
        default=2.0,
        ge=0.0,
        description="Delay between requests (rate limiting)",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts for failed requests",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Request timeout in seconds",
    )
    strip_query_params: bool = Field(
        default=True,
        description="Remove query parameters from URLs (for cleaner tracking)",
    )

    # Playwright browser settings
    use_playwright: bool = Field(
        default=True,
        description="Enable browser automation for JS-heavy sites",
    )
    headless: bool = Field(
        default=True,
        description="Run browser in headless mode (no UI). Set to False for Akamai sites in Docker.",
    )
    browser_type: BrowserType = Field(
        default=BrowserType.CHROMIUM,
        description="Browser engine: chromium, firefox, or webkit",
    )
    viewport_width: int = Field(
        default=1920,
        ge=320,
        le=7680,
        description="Browser viewport width (320-7680)",
    )
    viewport_height: int = Field(
        default=1080,
        ge=240,
        le=4320,
        description="Browser viewport height (240-4320)",
    )
    locale: str = Field(
        default="nl-NL",
        description="Browser locale (e.g., 'nl-NL', 'en-US')",
    )
    timezone: str = Field(
        default="Europe/Amsterdam",
        description="Browser timezone (e.g., 'Europe/Amsterdam')",
    )

    # Screenshot settings
    save_screenshots: bool = Field(
        default=False,
        description="Save screenshots on errors (debugging)",
    )
    screenshots_dir: str = Field(
        default="logs/screenshots",
        description="Screenshot directory",
    )

    @field_validator("screenshots_dir")
    @classmethod
    def validate_screenshots_dir(cls, value: str) -> str:
        """Validate and create screenshots directory if `save_screenshots` is enabled."""
        if value:
            path = Path(value)
            if path.is_absolute() and not path.parent.exists():
                return value
            path.mkdir(parents=True, exist_ok=True)
        return value


class WaitStrategy(str, Enum):
    """Supported Playwright wait strategies."""

    COMMIT = "commit"
    DOMCONTENTLOADED = "domcontentloaded"
    LOAD = "load"
    NETWORKIDLE = "networkidle"


class ProviderConfig(BaseModel):
    """Provider configuration for web scraping."""

    # Core provider identification
    name: str = Field(
        min_length=1,
        description="Provider name (unique identifier)",
    )
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code (e.g., 'NL', 'US')",
    )
    base_url: str = Field(
        min_length=1,
        description="Base URL for the provider (e.g., 'https://www.example.com')",
    )
    language: str | None = Field(
        default=None,
        description=(
            "Optional ISO 639-1 language code override (e.g., 'nl', 'de', 'en'). "
            "If not specified, language is detected from page HTML or inferred from country. "
            "Use this for sites with language different from country (e.g., German products on .nl domain)"
        ),
    )

    # Wait strategies
    wait_strategy: WaitStrategy = Field(
        default=WaitStrategy.DOMCONTENTLOADED,
        description="Playwright wait strategy",
    )
    wait_delay: int = Field(
        default=0,
        ge=0,
        le=30,
        description="Additional wait time in seconds (0-30)",
    )

    # Optional custom provider class
    custom_class: str | None = Field(
        default=None,
        description="Custom provider class name (e.g., 'CustomProvider')",
    )

    # Complex nested configs (kept as dict for flexibility in Phase 3)
    extraction: dict[str, Any] = Field(
        default_factory=dict,
        description="Extraction configuration (json_ld only)",
    )
    transformations: dict[str, Any] = Field(
        default_factory=dict,
        description="Data transformation rules (split, regex, etc.)",
    )
    product_pages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tracked product pages for this provider",
    )

    @field_validator("country")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        """Validate country code is uppercase 2-letter ISO code."""
        return v.upper()

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base URL starts with http:// or https://."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        # Remove trailing slash for consistency
        return v.rstrip("/")


class DatabaseConfig(BaseModel):
    """Database configuration with path validation."""

    url: str = Field(
        default="",
        description="Database URL or file path. Empty string uses platform-specific defaults.",
    )
    export_to_parquet: bool = Field(
        default=True,
        description="Export snapshots to Parquet files for DuckDB UI access",
    )
    parquet_path: str = Field(
        default="./data/snapshots.parquet",
        description="Parquet file location for UI reads",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Validate database URL format."""
        if not value or value.strip() == "":
            return ""

        if "://" in value:
            return value

        path = Path(value)
        if path.exists():
            return str(path.resolve())

        return value

    @field_validator("parquet_path")
    @classmethod
    def validate_parquet_path(cls, v: str) -> str:
        """Validate and normalize Parquet file path."""
        path = Path(v)

        path.parent.mkdir(parents=True, exist_ok=True)

        return str(path)


class CLIConfig(BaseModel):
    """CLI command configuration settings."""

    max_parallel_urls: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Maximum number of URLs allowed in parallel track command",
    )

    dev_mode: bool = Field(
        default=False,
        description=(
            "Enable developer mode with technical logging. "
            "Shows retry attempts, white page detection, extraction details, timestamps, "
            "log levels, and file paths. Default: false (clean user-friendly output)"
        ),
    )

    timezone: str = Field(
        default="Europe/Amsterdam",
        description="Timezone for datetime operations (e.g., 'Europe/Amsterdam', 'UTC')",
    )

    model_config = {"extra": "forbid"}


class ProductGroupPageConfig(BaseModel):
    """Individual page configuration within a product group."""

    url: str = Field(min_length=1, description="Product page URL")
    provider: str | None = Field(
        default=None, description="Optional provider name (auto-detected if omitted)"
    )

    model_config = {"extra": "forbid"}


class ProductGroupConfig(BaseModel):
    """Product group configuration for price comparison across stores."""

    name: str = Field(min_length=1, description="Unique product group name")
    description: str = Field(default="", description="Optional description of the product group")
    category: str | None = Field(default=None, description="Optional category for organization")
    pages: list[str | ProductGroupPageConfig] = Field(
        default_factory=list,
        description="List of product URLs (strings or dicts with url/provider)",
    )

    model_config = {"extra": "forbid"}

    @field_validator("pages", mode="before")
    @classmethod
    def normalize_pages(cls, v: Any) -> list[str | dict[str, Any]]:
        """Normalize pages to accept both strings and dicts."""
        if not isinstance(v, list):
            return []

        normalized: list[str | dict[str, Any]] = []
        for item in v:
            if isinstance(item, (str, dict)):
                normalized.append(item)
            else:
                continue

        return normalized


class AppConfig(BaseModel):
    """Root application configuration."""

    database: DatabaseConfig
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    providers: dict[str, ProviderConfig] = Field(
        default_factory=dict,
        description="Provider configurations keyed by provider name",
    )
    cli: CLIConfig = Field(default_factory=CLIConfig)
    product_groups: list[ProductGroupConfig] = Field(default_factory=list)

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }

    def get(self, key: str, default: Any = None) -> Any:
        """Backward compatibility method for dict-style access."""
        return getattr(self, key, default)
