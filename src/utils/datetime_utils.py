from datetime import datetime
from zoneinfo import ZoneInfo

from src.config.config_loader import load_typed_config


def get_configured_timezone(config_path: str | None = None) -> ZoneInfo:
    """
    Get configured timezone from config.yaml.

    Priority:
        1. cli.timezone (if set)
        2. scraping.timezone (fallback)
        3. `Europe/Amsterdam` (default)
    """
    config = load_typed_config(config_path)

    return ZoneInfo(config.cli.timezone or config.scraping.timezone)


def now_in_configured_tz(config_path: str | None = None) -> datetime:
    """Get current datetime in configured timezone."""
    tz = get_configured_timezone(config_path)
    # Get timezone-aware datetime, then remove timezone info
    # This preserves the local time (e.g., 06:30) without timezone conversion
    return datetime.now(tz).replace(tzinfo=None)


def to_configured_tz(dt: datetime, config_path: str | None = None) -> datetime:
    """Convert datetime to configured timezone."""
    tz = get_configured_timezone(config_path)

    if dt.tzinfo is None:
        from datetime import UTC

        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(tz)
