from typing import Any

from src.config.config_loader import load_typed_config as load_config


class ConfigDict(dict):
    """Dict subclass that provides attribute-style access."""

    def __getattr__(self, key: str) -> Any:
        """Allow attribute-style access to dict keys."""
        try:
            value = self[key]
            # Recursively wrap nested dicts
            if isinstance(value, dict) and not isinstance(value, ConfigDict):
                return ConfigDict(value)
            return value
        except KeyError as err:
            raise AttributeError(f"Config has no attribute '{key}'") from err

    def __setattr__(self, key: str, value: Any) -> None:
        """Allow attribute-style setting of dict keys."""
        self[key] = value


def get_config(config_path: str | None = None) -> ConfigDict:
    config_data = load_config(config_path)
    return ConfigDict(config_data)
