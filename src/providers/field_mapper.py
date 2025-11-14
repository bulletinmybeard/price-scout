import re
from typing import Any


class FieldMapper:
    """Maps field paths to values in JSON-LD structured data."""

    @staticmethod
    def get_value(
        data: dict[str, Any],
        path: str | list[str],
        default: Any = None,
        value_type: str | None = None,
    ) -> Any:
        """Extract value from nested data structure using path notation."""
        if isinstance(path, list):
            paths_to_try = path
            default_from_config = None

            if path and isinstance(path[-1], dict) and "default" in path[-1]:
                default_from_config = path[-1]["default"]
                paths_to_try = path[:-1]

            for single_path in paths_to_try:
                value = FieldMapper._extract_single_path(data, single_path)
                if value is not None:
                    return FieldMapper._convert_type(value, value_type)

            return default_from_config if default_from_config is not None else default

        value = FieldMapper._extract_single_path(data, path)
        if value is None:
            return default

        return FieldMapper._convert_type(value, value_type)

    @staticmethod
    def _extract_single_path(data: dict[str, Any], path: str) -> Any | None:
        """Extract value from a single path string."""
        if not path:
            return None

        current: Any = data
        parts = FieldMapper._parse_path(path)

        for part in parts:
            if current is None:
                return None

            if "[" in part and "]" in part:
                key, index = FieldMapper._parse_array_notation(part)
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
                if not isinstance(current, list) or index >= len(current):
                    return None
                current = current[index]
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    @staticmethod
    def _parse_path(path: str) -> list[str]:
        """Parse dot-notation path into parts."""
        parts = []
        current_part = ""

        for char in path:
            if char == ".":
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                current_part += char

        if current_part:
            parts.append(current_part)

        return parts

    @staticmethod
    def _parse_array_notation(part: str) -> tuple[str, int]:
        """Parse array notation into key and index."""
        match = re.match(r"^(.+)\[(\d+)\]$", part)
        if not match:
            raise ValueError(f"Invalid array notation: {part}")

        key = match.group(1)
        index = int(match.group(2))
        return key, index

    @staticmethod
    def _convert_type(value: Any, value_type: str | None) -> Any:
        """Convert value to specified type."""
        if value is None or value_type is None:
            return value

        try:
            if value_type == "str":
                return str(value)
            elif value_type == "int":
                return int(float(value))
            elif value_type == "float":
                return float(value)
            elif value_type == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ("true", "yes", "1", "on")
                return bool(value)
            else:
                return value
        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to convert {value} to {value_type}: {e}") from e

    @staticmethod
    def has_field(data: dict[str, Any], path: str | list[str]) -> bool:
        """Check if field exists in data structure."""
        value = FieldMapper.get_value(data, path)
        return value is not None
