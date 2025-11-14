import re
from typing import Any

from chalkbox.logging.bridge import get_logger

from src.utils.product_parser import _get_currency_symbols, normalize_unit_code

logger = get_logger(__name__)


class Transformations:
    """Collection of transformation functions for provider data."""

    @staticmethod
    def regex_replace(value: str, patterns: list[str], flags: int = re.IGNORECASE) -> str:
        """Remove/replace text using regex patterns."""
        if not value:
            return ""

        result = value
        for pattern in patterns:
            result = re.sub(pattern, "", result, flags=flags)

        return result.strip()

    @staticmethod
    def split_string(value: str, delimiter: str = ",", strip: bool = True) -> list[str]:
        """Split string into list."""
        if not value:
            return []

        if isinstance(value, list):
            return value  # Already a list

        parts = value.split(delimiter)

        if strip:
            parts = [part.strip() for part in parts]

        # Remove empty strings
        return [part for part in parts if part]

    @staticmethod
    def parse_price_specification(price_spec: dict[str, Any], currency: str = "EUR") -> str | None:
        """Parse priceSpecification object to formatted string."""
        try:
            price = price_spec.get("price")
            unit_code = price_spec.get("unitCode", "")

            if not price or not unit_code:
                return None

            price_float = float(price)

            unit = normalize_unit_code(unit_code)
            if not unit:
                unit = unit_code.lower()

            currency_symbols = _get_currency_symbols()
            symbol = currency_symbols.get(currency, currency)

            return f"{symbol}{price_float:.2f}/{unit}"

        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to parse price per unit: {e}")
            return None

    @staticmethod
    def parse_schema_availability(availability_url: str) -> bool:
        """
        Parse schema.org availability URL to boolean.

        Schema.org uses URLs like:
        - "https://schema.org/InStock" → True
        - "https://schema.org/OutOfStock" → False
        - "https://schema.org/PreOrder" → False
        """
        if not availability_url:
            return False

        url_lower = availability_url.lower()

        in_stock_patterns = ["instock", "in_stock", "available"]

        return any(pattern in url_lower for pattern in in_stock_patterns)

    @staticmethod
    def parse_price(
        value: str | float | None, config: dict[str, Any] | None = None
    ) -> float | None:
        """Parse and clean price string using config-driven rules."""
        if value is None or value == "":
            return None

        if isinstance(value, (int, float)):
            return float(value)

        price_str = str(value).strip()

        if not price_str:
            return None

        if config:
            price_str = Transformations._apply_price_cleaning_rules(price_str, config)
        else:
            price_str = Transformations._apply_basic_cleaning(price_str)

        try:
            decimal_format = "auto"
            if config:
                decimal_format = config.get("decimal_format", "auto")

            return Transformations._parse_decimal_format(price_str, decimal_format)

        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse price '{value}': {e}")
            return None

    @staticmethod
    def _apply_basic_cleaning(price_str: str) -> str:
        """Apply basic price cleaning (common symbols and whitespace)."""
        price_str = " ".join(price_str.split())

        for symbol in ["€", "$", "£", "USD", "EUR", "GBP", "\xa0", "\u00a0"]:
            price_str = price_str.replace(symbol, "")

        return price_str.strip()

    @staticmethod
    def _apply_price_cleaning_rules(price_str: str, config: dict[str, Any]) -> str:
        """Apply config-driven price cleaning rules."""

        price_str = " ".join(price_str.split())

        prefixes = config.get("remove_prefixes", [])
        for prefix in prefixes:
            pattern = rf"^{re.escape(prefix)}\s*"
            price_str = re.sub(pattern, "", price_str, flags=re.IGNORECASE)

        default_symbols = ["€", "$", "£", "USD", "EUR", "GBP", "\xa0", "\u00a0"]
        config_symbols = config.get("remove_symbols", [])
        all_symbols = list(set(default_symbols + config_symbols))  # Deduplicate

        for symbol in all_symbols:
            price_str = price_str.replace(symbol, "")
        price_str = price_str.strip()

        format_rules = config.get("format_rules", [])
        for rule in format_rules:
            if isinstance(rule, dict) and "pattern" in rule and "replacement" in rule:
                pattern = rule["pattern"]
                replacement = rule["replacement"]
                price_str = re.sub(pattern, replacement, price_str)

        return str(price_str.strip())

    @staticmethod
    def _parse_decimal_format(price_str: str, decimal_format: str = "auto") -> float:
        """Parse decimal format from cleaned price string."""
        price_str = price_str.strip()

        if decimal_format == "auto":
            comma_count = price_str.count(",")
            dot_count = price_str.count(".")

            # If both exist, last one is decimal separator
            if comma_count > 0 and dot_count > 0:
                last_comma_pos = price_str.rfind(",")
                last_dot_pos = price_str.rfind(".")

                decimal_format = "eu" if last_comma_pos > last_dot_pos else "us"
            # Only comma = European
            elif comma_count > 0:
                decimal_format = "eu"
            # Only dot or neither = US
            else:
                decimal_format = "us"

        if decimal_format == "eu":
            # European: "1.234,56" → 1234.56
            if "," in price_str:
                price_str = price_str.replace(".", "")
                price_str = price_str.replace(",", ".")
            elif "." in price_str:
                parts = price_str.split(".")
                if len(parts) == 2 and len(parts[1]) <= 2:
                    pass
                else:
                    price_str = price_str.replace(".", "")
        else:
            price_str = price_str.replace(",", "")  # Remove thousand separator

        return float(price_str)

    @staticmethod
    def apply_transformation(value: Any, transformation: dict[str, Any] | None = None) -> Any:
        """Apply a transformation based on config rules."""

        if not transformation:
            return value

        if not isinstance(transformation, dict):
            return value

        transform_type = transformation.get("type")

        if transform_type == "regex_replace":
            patterns = transformation.get("patterns", [])
            return Transformations.regex_replace(value, patterns)

        elif transform_type == "split":
            delimiter = transformation.get("delimiter", ",")
            return Transformations.split_string(value, delimiter)

        elif transform_type == "price_specification":
            currency = transformation.get("currency", "EUR")
            return Transformations.parse_price_specification(value, currency)

        elif transform_type == "schema_availability":
            return Transformations.parse_schema_availability(value)

        elif transform_type == "parse_price":
            # Extract config for parse_price (everything except 'type')
            config = {k: v for k, v in transformation.items() if k != "type"}
            return Transformations.parse_price(value, config if config else None)

        logger.warning(f"Unknown transformation type: {transform_type}")
        return value
