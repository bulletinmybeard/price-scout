from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.utils.datetime_utils import now_in_configured_tz


@dataclass
class TrackedProduct:
    """Product page tracked for price monitoring."""

    # ===================================================================
    # IDENTITY (Required)
    # ===================================================================
    provider: str  # Provider name
    url: str  # Product page URL to track

    # ===================================================================
    # CONFIGURATION
    # ===================================================================
    enabled: bool = True  # Whether to actively track this page
    name: str | None = None  # Human-readable product name/description

    # ===================================================================
    # METADATA
    # ===================================================================
    tags: list[str] = field(default_factory=list[str])  # Categorization tags
    notes: str | None = None  # User notes

    # ===================================================================
    # TRACKING STATE (Not in config, populated at runtime)
    # ===================================================================
    last_checked: datetime | None = None  # Last check timestamp
    last_price: float | None = None  # Last known price
    created_at: datetime = field(default_factory=now_in_configured_tz)  # When added

    @classmethod
    def from_dict(cls, data: dict[str, Any], provider: str | None = None) -> "TrackedProduct":
        """Create TrackedProduct from config dictionary."""
        provider_value = data.get("provider", provider)
        if provider_value is None:
            raise ValueError("Provider must be specified either in data or as argument")
        return cls(
            provider=provider_value,
            url=data["url"],
            enabled=data.get("enabled", True),
            name=data.get("name"),
            tags=data.get("tags", []),
            notes=data.get("notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for saving back to config)."""
        return {
            "provider": self.provider,
            "url": self.url,
            "enabled": self.enabled,
            "name": self.name,
            "tags": self.tags,
            "notes": self.notes,
        }

    def __repr__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"<TrackedProduct({self.provider}): {self.name or self.url[:50]} [{status}]>"
