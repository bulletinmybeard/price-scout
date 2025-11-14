import json
import os
from pathlib import Path
import shutil
from typing import Any

from chalkbox.logging.bridge import get_logger
from pydantic import ValidationError
import yaml

from src.config.models import AppConfig

logger = get_logger(__name__)

USER_DIRECTORY_NAME = ".price-scout"


def is_docker_environment() -> bool:
    """Detect if the app is running in a Docker container.

    Checks for:
    - IN_DOCKER environment variable set to `1`
    - /.dockerenv file (standard Docker indicator)
    """
    return os.getenv("IN_DOCKER") == "1" or Path("/.dockerenv").exists()


def is_development_environment() -> bool:
    """Detect if the app is running in development environment (poetry/local repo)."""
    if is_docker_environment():
        return False

    try:
        current = Path.cwd()
        while current != current.parent:
            git_dir = current / ".git"
            pyproject = current / "pyproject.toml"

            if git_dir.exists() and pyproject.exists():
                return True

            current = current.parent

        return False
    except Exception:
        return False


def get_user_directory() -> Path:
    """Get user config directory for global installations."""
    return Path.home() / USER_DIRECTORY_NAME


def get_provider_configs_directory() -> Path:
    """Get provider configs directory based on environment."""
    if is_docker_environment():
        return Path("/app/provider_configs")
    elif is_development_environment():
        return Path(__file__).parent.parent.parent / "provider_configs"

    return get_user_directory() / "provider_configs"


def copy_bundled_provider_configs() -> bool:
    """Copy bundled provider configs to user directory."""
    user_configs_dir = get_user_directory() / "provider_configs"
    user_configs_dir.mkdir(parents=True, exist_ok=True)

    try:
        bundled_configs_path = Path(__file__).parent.parent.parent / "provider_configs"

        if not bundled_configs_path.exists():
            logger.warning(f"Bundled provider configs not found at: {bundled_configs_path}")
            return False

        copied_count = 0
        for config_file in bundled_configs_path.glob("*.yaml"):
            if any(skip in config_file.name.lower() for skip in ["example", "readme", "config-"]):
                continue

            if "." in config_file.stem:
                continue

            target = user_configs_dir / config_file.name
            if not target.exists():
                shutil.copy(config_file, target)
                copied_count += 1
                logger.debug(f"Copied provider config: {config_file.name}")

        if copied_count > 0:
            logger.debug(f"Copied {copied_count} provider configs to: {user_configs_dir}")

        return True

    except Exception as e:
        logger.error(f"Failed to copy bundled provider configs: {e}")
        return False


def ensure_user_directory() -> bool:
    """
    Ensure user directory exists.

    Creates:
    - ~/.price-scout/
    - ~/.price-scout/provider_configs/
    - ~/.price-scout/config.yaml (from example)
    - ~/.price-scout/product_parser_defaults.yaml
    """
    if is_development_environment():
        return True

    user_dir = get_user_directory()
    config_file = user_dir / "config.yaml"
    provider_configs_dir = user_dir / "provider_configs"
    parser_defaults_file = user_dir / "product_parser_defaults.yaml"

    try:
        user_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured user directory exists: {user_dir}")
    except OSError as e:
        logger.error(f"Failed to create user directory: {e}")
        return False

    if not provider_configs_dir.exists() or not any(provider_configs_dir.glob("*.yaml")):
        logger.debug("Initializing provider configs...")
        if not copy_bundled_provider_configs():
            logger.warning("Failed to copy provider configs")
            return False

    if not config_file.exists():
        bundled_example = Path(__file__).parent.parent.parent / "config.example.yaml"

        if bundled_example.exists():
            try:
                shutil.copy(bundled_example, config_file)
                logger.debug(f"Created config file: {config_file}")
            except OSError as e:
                logger.error(f"Failed to create config file: {e}")
                return False
        else:
            logger.warning("Bundled config.example.yaml not found")

    if not parser_defaults_file.exists():
        bundled_parser_defaults = (
            Path(__file__).parent.parent.parent
            / "provider_configs"
            / "product_parser_defaults.yaml"
        )

        if bundled_parser_defaults.exists():
            try:
                shutil.copy(bundled_parser_defaults, parser_defaults_file)
                logger.debug(f"Created product parser defaults: {parser_defaults_file}")
            except OSError as e:
                logger.error(f"Failed to create product parser defaults: {e}")
                # Non-fatal - fallback to package data will work

    return True


def get_default_config_path() -> Path:
    """
    Get default config path.

    Priority order:
    1. DOCKER CONTAINER: /app/config.yaml
    2. LOCAL DEVELOPMENT (poetry): ./config.yaml (project root)
    3. GLOBAL INSTALLATION: ~/.price-scout/config.yaml

    Never creates files in home directory when running from local development or Docker.
    """
    if is_docker_environment():
        return Path("/app/config.yaml")

    if is_development_environment():
        return Path(__file__).parent.parent.parent / "config.yaml"

    # Global installation: use user directory
    # Ensure directory exists and is populated
    ensure_user_directory()
    return get_user_directory() / "config.yaml"


class ConfigLoader:
    """Load and validate configuration from YAML files."""

    def __init__(self, config_path: str | Path | None = None):
        """Initialize config loader."""
        if config_path is None:
            config_path = get_default_config_path()

        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self._pydantic_config: AppConfig | None = None

    @staticmethod
    def _find_bundled_example() -> Path | None:
        """Find the bundled config.example.yaml file."""
        candidates = [
            Path("/app/config.example.yaml"),
            Path(__file__).parent.parent.parent / "config.example.yaml",
            Path(__file__).parent.parent / "config.example.yaml",
            Path.cwd() / "config.example.yaml",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _create_default_config(self) -> bool:
        """Create default config from bundled example."""
        bundled_example = self._find_bundled_example()

        if not bundled_example:
            return False

        try:
            shutil.copy(bundled_example, self.config_path)

            logger.debug(f"Created default config at: {self.config_path}")
            logger.debug(f"Copied from: {bundled_example}")
            logger.debug("Please review and customize for your needs")

            return True

        except OSError as e:
            logger.error(f"Failed to create default config: {e}")
            return False

    def load(self) -> dict[str, Any]:
        """Load configuration from YAML file.

        Auto-creates config from bundled example on first run if not found.
        """
        if not self.config_path.exists():
            logger.debug(f"Config not found at: {self.config_path}")

            if self._create_default_config():
                logger.debug("Using default configuration")
            else:
                raise FileNotFoundError(
                    f"Config file not found: {self.config_path}\n"
                    f"Could not find bundled config.example.yaml to create default config.\n"
                    f"Please create config manually or run: price-scout config init"
                )

        try:
            with open(self.config_path, encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

            logger.debug(f"Loaded configuration from: {self.config_path}")

            self._log_config_summary()

            return self.config

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse {self.config_path.name}: {e}")
            raise

    def load_typed(self) -> AppConfig:
        """Load configuration and return as validated Pydantic model."""
        if not self.config:
            self.load()

        try:
            self._pydantic_config = AppConfig(**self.config)
            logger.debug("Configuration validated successfully")
            return self._pydantic_config

        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            logger.error(f"Config file: {self.config_path}")
            logger.error("Please check your config.yaml against config.example.yaml")
            raise

    def _log_config_summary(self):
        """Log summary of loaded configuration."""
        product_groups = self.config.get("product_groups", [])
        providers = self.config.get("providers", {})
        database_url = self.config.get("database", {}).get("url", "not configured")

        logger.debug(f"  Database: {database_url}")
        logger.debug(f"  Product groups: {len(product_groups)}")
        logger.debug(f"  Providers: {len(providers)}")

        groups_with_metadata = sum(
            1
            for g in product_groups
            if g.get("category") or g.get("weekly_usage") or g.get("meal_type")
        )
        if groups_with_metadata:
            logger.debug(f"  Groups with metadata: {groups_with_metadata}")

    def to_json(self) -> str:
        """Export configuration as JSON string."""
        return json.dumps(self.config, indent=2)

    def __repr__(self) -> str:
        """String representation."""
        return f"ConfigLoader(config_path={self.config_path})"


def load_typed_config(config_path: str | Path | None = None) -> AppConfig:
    """Convenience function to load typed configuration."""
    loader = ConfigLoader(config_path)
    return loader.load_typed()
