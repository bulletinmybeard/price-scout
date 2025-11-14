from pathlib import Path
from typing import Any

from chalkbox.logging.bridge import get_logger
from pydantic import ValidationError
import yaml

from src import providers
from src.config.config_loader import ConfigLoader, get_provider_configs_directory
from src.config.models import ProviderConfig
from src.providers.configurable_provider import ConfigurableProvider
from src.scrapers.async_base_provider import AsyncBaseProvider

logger = get_logger(__name__)


class ProviderFactory:
    """Factory for creating provider instances."""

    def __init__(self, config_path: str | None = None, provider_config_override: str | None = None):
        """Initialize the provider factory."""
        self.config_loader = ConfigLoader(config_path)
        self.provider_config_override = provider_config_override
        self.full_config, self.config = self._load_config()

    def _load_config(self) -> tuple[dict[str, Any], dict[str, ProviderConfig]]:
        """
        Load provider configurations from config.yaml and provider_configs/ directory.

        Priority (highest to lowest):
        1. Explicit override file (via provider_config_override parameter) - HIGHEST
        2. config.yaml providers section (user's explicit configuration)
        3. provider_configs/*.yaml files (system defaults/fallbacks) - LOWEST
        """
        providers: dict[str, ProviderConfig] = {}

        if self.provider_config_override:
            override_path = Path(self.provider_config_override)

            if not override_path.is_absolute():
                override_path = Path.cwd() / self.provider_config_override

            if not override_path.exists():
                override_path = get_provider_configs_directory() / self.provider_config_override

            if override_path.exists():
                try:
                    with open(override_path, encoding="utf-8") as f:
                        provider_dict = yaml.safe_load(f)

                    if provider_dict and isinstance(provider_dict, dict):
                        try:
                            provider_config = ProviderConfig(**provider_dict)
                            provider_name = provider_config.name
                            providers[provider_name] = provider_config
                            logger.debug(f"Loaded override provider config from: {override_path}")
                        except ValidationError as e:
                            logger.error(f"Invalid provider config in {override_path}: {e}")
                            raise
                    else:
                        logger.warning(f"Invalid override provider config: {override_path}")
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse override config {override_path}: {e}")
            else:
                logger.warning(
                    f"Override provider config not found: {self.provider_config_override}"
                )

            full_config = self.config_loader.load()
            return full_config, providers

        full_config = self.config_loader.load()
        providers_raw = full_config.get("providers", {})

        for provider_name, provider_dict in providers_raw.items():
            try:
                providers[provider_name] = ProviderConfig(**provider_dict)
            except ValidationError as e:
                logger.error(f"Invalid provider config '{provider_name}' in config.yaml: {e}")
                raise

        if providers:
            logger.debug(f"Loaded {len(providers)} providers from config.yaml")

        provider_configs_dir = get_provider_configs_directory()

        if provider_configs_dir.exists() and provider_configs_dir.is_dir():
            yaml_files = list(provider_configs_dir.glob("*.yaml")) + list(
                provider_configs_dir.glob("*.yml")
            )

            for yaml_file in yaml_files:
                if yaml_file.name.startswith(("README", "readme", "example-", "config-")):
                    logger.debug(f"Skipping documentation file: {yaml_file.name}")
                    continue

                if yaml_file.name == "product_parser_defaults.yaml":
                    logger.debug(f"Skipping product parser config: {yaml_file.name}")
                    continue

                if "." in yaml_file.stem:
                    logger.debug(f"Skipping variant config: {yaml_file.name}")
                    continue

                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        provider_dict = yaml.safe_load(f)

                    if not provider_dict or not isinstance(provider_dict, dict):
                        logger.warning(f"Skipping invalid provider config: {yaml_file.name}")
                        continue

                    try:
                        provider_config = ProviderConfig(**provider_dict)
                        provider_name = provider_config.name

                        if provider_name not in providers:
                            providers[provider_name] = provider_config
                            logger.debug(f"Loaded provider '{provider_name}' from {yaml_file.name}")
                        else:
                            logger.debug(
                                f"Skipping '{yaml_file.name}' - '{provider_name}' already defined in config.yaml"
                            )
                    except ValidationError as e:
                        logger.error(f"Invalid provider config in {yaml_file.name}: {e}")
                        continue

                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse {yaml_file.name}: {e}")
                    continue

            if yaml_files:
                logger.debug(
                    f"Loaded {len(yaml_files)} provider configs from provider_configs/ directory"
                )

        if not providers:
            logger.warning("No provider configurations found")

        logger.debug(f"Total providers available: {len(providers)}")
        return full_config, providers

    def get_provider(self, provider_name: str, headless: bool = True) -> AsyncBaseProvider:
        """Get a provider instance by name."""
        if provider_name not in self.config:
            available = ", ".join(self.config.keys())
            raise ValueError(
                f"Provider '{provider_name}' not found in config. Available providers: {available}"
            )

        provider_config = self.config[provider_name]

        custom_class_name = provider_config.custom_class
        if custom_class_name:
            logger.debug(f"Loading custom provider class: {custom_class_name}")

            try:
                custom_class = getattr(providers, custom_class_name)
                return custom_class(headless=headless)
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to load custom provider class '{custom_class_name}': {e}")
                raise ValueError(
                    f"Custom provider class '{custom_class_name}' not found in src.providers"
                ) from e

        logger.debug(f"Loading config-based provider: {provider_name}")
        return ConfigurableProvider(config=provider_config, headless=headless)

    def list_providers(self) -> list[str]:
        """Get list of available provider names."""
        return sorted(self.config.keys())

    def reload_config(self):
        """Reload configuration from config.yaml."""
        logger.debug("Reloading provider configuration")
        self.full_config, self.config = self._load_config()


# Global factory instance
_factory_instance: ProviderFactory | None = None


def get_factory(
    config_path: str | None = None, provider_config: str | None = None
) -> ProviderFactory:
    """Get or create the global provider factory instance."""
    global _factory_instance

    if _factory_instance is None or config_path is not None or provider_config is not None:
        _factory_instance = ProviderFactory(
            config_path=config_path, provider_config_override=provider_config
        )

    return _factory_instance
