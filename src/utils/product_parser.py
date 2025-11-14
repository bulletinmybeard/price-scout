from importlib.resources import files
from pathlib import Path
import re
from typing import Any

from chalkbox.logging.bridge import get_logger
import yaml

logger = get_logger(__name__)

# Configuration caches (lazy-loaded from YAML)
_default_variants_cache: dict[str, Any] | None = None
_unit_code_map_cache: dict[str, Any] | None = None
_country_language_map_cache: dict[str, Any] | None = None
_count_units_cache: set[str] | None = None
_currency_symbols_cache: dict[str, Any] | None = None


def _get_unit_code_map() -> dict[str, Any]:
    """Load unit code mappings from YAML (lazy-loaded, cached)."""
    global _unit_code_map_cache

    if _unit_code_map_cache is not None:
        return _unit_code_map_cache

    paths = _get_config_paths()
    for path in paths:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if "units" in config:
                    _unit_code_map_cache = config["units"]
                    logger.debug(f"Loaded unit mappings from {path}")
                    return _unit_code_map_cache
            except Exception as e:
                logger.debug(f"Failed to load units from {path}: {e}")
                continue

    logger.warning("Could not load unit mappings from YAML. Using minimal fallback.")
    _unit_code_map_cache = {"KGM": "kg", "GRM": "g", "LTR": "l", "MLT": "ml"}
    return _unit_code_map_cache


def _get_country_language_map() -> dict:
    """Load country-to-language mappings from YAML (lazy-loaded, cached)."""
    global _country_language_map_cache

    if _country_language_map_cache is not None:
        return _country_language_map_cache

    paths = _get_config_paths()
    for path in paths:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if "countries" in config:
                    _country_language_map_cache = config["countries"]
                    logger.debug(f"Loaded country mappings from {path}")
                    return _country_language_map_cache
            except Exception as e:
                logger.debug(f"Failed to load countries from {path}: {e}")
                continue

    logger.warning("Could not load country mappings from YAML. Using minimal fallback.")
    _country_language_map_cache = {"NL": "nl", "DE": "de", "FR": "fr", "GB": "en", "US": "en"}
    return _country_language_map_cache


def _get_count_units() -> set[str]:
    """Load count units from YAML (lazy-loaded, cached)."""
    global _count_units_cache

    if _count_units_cache is not None:
        return _count_units_cache

    paths = _get_config_paths()
    for path in paths:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if "count_units" in config:
                    _count_units_cache = set(config["count_units"])
                    logger.debug(f"Loaded count units from {path}")
                    return _count_units_cache
            except Exception as e:
                logger.debug(f"Failed to load count_units from {path}: {e}")
                continue

    logger.warning("Could not load count units from YAML. Using minimal fallback.")
    _count_units_cache = {"st", "pcs", "units"}
    return _count_units_cache


def _get_currency_symbols() -> dict:
    """Load currency symbols from YAML (lazy-loaded, cached)."""
    global _currency_symbols_cache

    if _currency_symbols_cache is not None:
        return _currency_symbols_cache

    paths = _get_config_paths()
    for path in paths:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if "currency_symbols" in config:
                    _currency_symbols_cache = config["currency_symbols"]
                    logger.debug(f"Loaded currency symbols from {path}")
                    return _currency_symbols_cache
            except Exception as e:
                logger.debug(f"Failed to load currency_symbols from {path}: {e}")
                continue

    logger.warning("Could not load currency symbols from YAML. Using minimal fallback.")
    _currency_symbols_cache = {"EUR": "€", "USD": "$", "GBP": "£"}
    return _currency_symbols_cache


# Helper functions for dynamic pattern generation
def _get_all_unit_variants() -> set[str]:
    """Extract all unique unit variations from unit code map (keys and values)."""
    units = set()
    unit_map = _get_unit_code_map()
    for key, value in unit_map.items():
        units.add(key)  # UN/CEFACT codes and variations
        units.add(value)  # Normalized units
    return units


def _build_unit_pattern(exclude: set[str] | None = None) -> str:
    """Build a regex alternation pattern for units."""
    units = _get_all_unit_variants()
    if exclude:
        units = units - exclude

    sorted_units = sorted(units, key=len, reverse=True)
    escaped_units = [re.escape(unit) for unit in sorted_units]
    return "|".join(escaped_units)


# Pattern caches (lazy-built after loading YAML config)
_WEIGHT_VOLUME_PATTERN_CACHE: str | None = None
_COUNT_PATTERN_CACHE: str | None = None
_COUNT_UNIT_PATTERN_CACHE: str | None = None
_AMOUNT_PATTERNS_CACHE: list | None = None
_MULTIPACK_PATTERNS_CACHE: tuple | None = None


def _get_weight_volume_pattern() -> str:
    """Get weight/volume pattern (lazy-built, cached)."""
    global _WEIGHT_VOLUME_PATTERN_CACHE
    if _WEIGHT_VOLUME_PATTERN_CACHE is None:
        count_units = _get_count_units()
        _WEIGHT_VOLUME_PATTERN_CACHE = _build_unit_pattern(exclude=count_units)
    return _WEIGHT_VOLUME_PATTERN_CACHE


def _get_count_pattern() -> str:
    """Get all units pattern including count (lazy-built, cached)."""
    global _COUNT_PATTERN_CACHE
    if _COUNT_PATTERN_CACHE is None:
        _COUNT_PATTERN_CACHE = _build_unit_pattern()
    return _COUNT_PATTERN_CACHE


def _get_count_unit_pattern() -> str:
    """Get count units only pattern (lazy-built, cached)."""
    global _COUNT_UNIT_PATTERN_CACHE
    if _COUNT_UNIT_PATTERN_CACHE is None:
        count_units = _get_count_units()
        _COUNT_UNIT_PATTERN_CACHE = "|".join(
            sorted([re.escape(u) for u in count_units], key=len, reverse=True)
        )
    return _COUNT_UNIT_PATTERN_CACHE


def _get_amount_patterns() -> list:
    """Get amount extraction patterns (lazy-built, cached)."""
    global _AMOUNT_PATTERNS_CACHE
    if _AMOUNT_PATTERNS_CACHE is None:
        count_pattern = _get_count_pattern()
        weight_volume_pattern = _get_weight_volume_pattern()
        count_unit_pattern = _get_count_unit_pattern()

        _AMOUNT_PATTERNS_CACHE = [
            # Range format: "100-200g" -> take first value
            re.compile(
                rf"(\d+(?:[,.]\d+)?)\s*-\s*\d+(?:[,.]\d+)?\s*({count_pattern})",
                re.IGNORECASE,
            ),
            # Weight/volume units (priority over count): "500 g", "1.5 kg", "330 ml"
            re.compile(rf"(\d+(?:[,.]\d+)?)\s*({weight_volume_pattern})", re.IGNORECASE),
            # Count units (checked last): "6 st", "12 stuks"
            re.compile(rf"(\d+)\s*({count_unit_pattern})", re.IGNORECASE),
        ]
    return _AMOUNT_PATTERNS_CACHE


def _get_multipack_patterns() -> tuple:
    """Get multipack extraction patterns (lazy-built, cached)."""
    global _MULTIPACK_PATTERNS_CACHE
    if _MULTIPACK_PATTERNS_CACHE is None:
        count_pattern = _get_count_pattern()
        _MULTIPACK_PATTERNS_CACHE = (
            re.compile(rf"(\d+)\s*x\s*(\d+(?:[,.]\d+)?)\s*({count_pattern})", re.IGNORECASE),
            re.compile(r"(\d+)[-\s]*(pack|x)\b", re.IGNORECASE),
        )
    return _MULTIPACK_PATTERNS_CACHE


def _get_config_paths() -> list[Path]:
    """
    Get potential paths for default config in priority order.

    Search order:
    1. Development environment (project root/config/)
    2. Installed package data (site-packages)
    3. User config directory (~/.price-scout/) - auto-created on first use
    """
    paths = []

    # Development environment (project root/provider_configs/)
    dev_path = (
        Path(__file__).parent.parent.parent / "provider_configs" / "product_parser_defaults.yaml"
    )
    paths.append(dev_path)

    # Installed package data
    try:
        src_files = files("src")
        if hasattr(src_files, "parent"):
            pkg_path = src_files.parent / "provider_configs" / "product_parser_defaults.yaml"  # type: ignore[attr-defined]
            paths.append(Path(str(pkg_path)))
    except Exception as e:
        logger.debug(f"Could not load package resource path: {e}")

    # User config directory (auto-created on first use)
    user_config = Path.home() / ".price-scout" / "product_parser_defaults.yaml"
    if user_config.exists():
        paths.append(user_config)

    return paths


def _load_default_variants() -> dict:
    """
    Load default variants from YAML file (lazy-loaded, cached).

    Search order:
    1. provider_configs/product_parser_defaults.yaml (development)
    2. Package data (installed via pip)
    3. User config directory (if exists)
    4. Minimal hardcoded fallback (emergency only)
    """
    global _default_variants_cache

    if _default_variants_cache is not None:
        return _default_variants_cache

    paths = _get_config_paths()
    for path in paths:
        if path.exists():
            try:
                _default_variants_cache = load_variant_config(path)
                logger.debug(f"Loaded default variants from {path}")
                return _default_variants_cache
            except Exception as e:
                logger.warning(f"Failed to load variants from {path}: {e}")
                continue

    logger.error(
        "Could not load product_parser_defaults.yaml from any location. "
        "Using minimal fallback. Please ensure config file is present."
    )
    _default_variants_cache = {
        "colors": {"en": ["red", "blue", "green", "black", "white"]},
        "flavors": {"en": ["chocolate", "vanilla", "strawberry"]},
        "types": {"en": ["organic", "vegan", "vegetarian"]},
    }
    return _default_variants_cache


def _get_flat_variant_list(
    category: str, variants_dict: dict | None = None, language: str | None = None
) -> list[str]:
    """Generate a flat list of variants for a category."""
    source = variants_dict or _load_default_variants()
    category_data = source.get(category, {})

    if language:
        return category_data.get(language, [])

    variants = []
    for lang_variants in category_data.values():
        variants.extend(lang_variants)
    return variants


def _validate_variants_config(config: dict) -> list[str]:
    """Validate variant configuration structure."""
    errors = []

    if "variants" not in config:
        errors.append("Missing 'variants' key in configuration")
        return errors

    variants = config["variants"]
    if not isinstance(variants, dict):
        errors.append("'variants' must be a dictionary")
        return errors

    for category, languages in variants.items():
        if not isinstance(languages, dict):
            errors.append(f"Category '{category}' must be a dictionary of languages")
            continue

        for language, variant_list in languages.items():
            if not isinstance(variant_list, list):
                errors.append(f"Language '{language}' in category '{category}' must be a list")
                continue

            for i, variant in enumerate(variant_list):
                if not isinstance(variant, str):
                    errors.append(
                        f"Variant {i} in '{category}.{language}' must be a string, got {type(variant)}"
                    )

    return errors


def _check_cross_category_duplicates(variants: dict) -> list[str]:
    """Check for variants that appear in multiple categories."""
    warnings = []

    category_variants: dict[str, set[str]] = {}
    for category, languages in variants.items():
        category_variants[category] = set()
        for lang_variants in languages.values():
            category_variants[category].update(v.lower() for v in lang_variants)

    categories = list(category_variants.keys())
    for i, cat1 in enumerate(categories):
        for cat2 in categories[i + 1 :]:
            duplicates = category_variants[cat1] & category_variants[cat2]
            if duplicates:
                warnings.append(f"Variants {duplicates} appear in both '{cat1}' and '{cat2}'")

    return warnings


def load_variant_config(config_path: str | Path | None = None) -> dict:
    """Load variant configuration from YAML file."""
    if config_path is None:
        return _load_default_variants()

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in {config_path}: {e}") from e

    errors = _validate_variants_config(config)
    if errors:
        raise ValueError("Invalid config structure:\n" + "\n".join(f"  - {e}" for e in errors))

    warnings = _check_cross_category_duplicates(config["variants"])
    for warning in warnings:
        logger.warning(f"Variant config: {warning}")

    logger.debug(f"Loaded variant config from {config_path}")
    return config["variants"]


def merge_variant_configs(base: dict, override: dict) -> dict:
    """
    Merge two variant configurations, with override taking precedence.

    Merge strategy:
    - If override defines a category, it completely replaces the base category
    - If override defines a language within a category, it extends/overrides base variants
    """
    merged: dict[str, dict[str, list[str]]] = {}

    for category in base:
        merged[category] = {}

        base_languages = base[category]
        override_languages = override.get(category, {})

        for lang, variants in base_languages.items():
            merged[category][lang] = list(variants)  # Copy list

        for lang, variants in override_languages.items():
            merged[category][lang] = list(variants)  # Replace completely

    for category in override:
        if category not in merged:
            merged[category] = {}
            for lang, variants in override[category].items():
                merged[category][lang] = list(variants)

    logger.debug(f"Merged variant configs: {len(merged)} categories")
    return merged


def normalize_unit_code(unit: str) -> str:
    """Normalize UN/CEFACT codes and common variations to human-readable units."""
    if not unit:
        return ""

    unit_clean = unit.strip()

    unit_map = _get_unit_code_map()

    normalized = unit_map.get(unit_clean.upper())
    if normalized:
        return normalized

    normalized = unit_map.get(unit_clean.lower())
    if normalized:
        return normalized

    return unit_clean.lower()


def _normalize_un_cefact_in_text(text: str) -> str:
    """Replace all UN/CEFACT codes in text with normalized units."""
    if not text:
        return text

    result = text
    unit_map = _get_unit_code_map()
    for code, normalized_unit in unit_map.items():
        result = re.sub(
            r"\b" + re.escape(code) + r"\b",
            normalized_unit,
            result,
            flags=re.IGNORECASE,
        )
    return result


def extract_amount_and_unit(text: str) -> tuple[float | None, str | None]:
    """
    Extract numeric amount and unit from text.

    Supports:
    - Weight: "500 g", "1.5 kg", "2kg"
    - Volume: "1 l", "500 ml", "330ml"
    - Count: "6 st", "12 stuks"
    - Ranges: "100-200g" (returns first value)
    """
    if not text:
        return None, None

    text_clean = text.strip()

    for pattern in _get_amount_patterns():
        match = pattern.search(text_clean)
        if match:
            amount_str = match.group(1).replace(",", ".")  # European decimal
            unit_str = match.group(2)

            try:
                amount_value = float(amount_str)
                amount_unit = normalize_unit_code(unit_str)
                logger.debug(f"Extracted amount: {amount_value} {amount_unit} from '{text}'")
                return amount_value, amount_unit
            except ValueError:
                logger.warning(f"Failed to parse amount '{amount_str}' from '{text}'")
                continue

    logger.debug(f"No amount found in '{text}'")
    return None, None


def extract_pack_info(text: str) -> tuple[int, float | None, str | None]:
    """
    Extract multi-pack information from text.

    Supports:
    - "6 x 330ml" -> (6, 330.0, "ml")
    - "3 x 1kg" -> (3, 1.0, "kg")
    - "12-pack" -> (12, None, None)
    - "6x" -> (6, None, None)
    """
    if not text:
        return 1, None, None

    text_clean = text.strip()

    multipack_with_amount, multipack_count_only = _get_multipack_patterns()

    # Multi-pack with amount: "6 x 330ml", "3 x 1kg"
    match = multipack_with_amount.search(text_clean)
    if match:
        try:
            pack_count = int(match.group(1))
            amount_str = match.group(2).replace(",", ".")
            amount_value = float(amount_str)
            unit_str = match.group(3)
            unit = normalize_unit_code(unit_str)

            logger.debug(
                f"Extracted multi-pack: {pack_count} x {amount_value} {unit} from '{text}'"
            )
            return pack_count, amount_value, unit
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse multi-pack with amount from '{text}': {e}")

    # Multi-pack without amount: "12-pack", "6x"
    match = multipack_count_only.search(text_clean)
    if match:
        try:
            pack_count = int(match.group(1))
            logger.debug(f"Extracted pack count: {pack_count} from '{text}'")
            return pack_count, None, None
        except ValueError as e:
            logger.warning(f"Failed to parse pack count from '{text}': {e}")

    # Not a multi-pack
    return 1, None, None


def extract_variants(
    text: str,
    custom_variants: dict | None = None,
    language: str | None = None,
) -> dict[str, str | None]:
    """Extract variant information (color, flavor, type) from text."""
    if not text:
        return {"variant_color": None, "variant_flavor": None, "variant_type": None}

    text_lower = text.lower()

    colors = _get_flat_variant_list("colors", custom_variants, language)
    flavors = _get_flat_variant_list("flavors", custom_variants, language)
    types = _get_flat_variant_list("types", custom_variants, language)

    result: dict[str, str | None] = {
        "variant_color": None,
        "variant_flavor": None,
        "variant_type": None,
    }

    for color in colors:
        if re.search(r"\b" + re.escape(color) + r"\b", text_lower):
            result["variant_color"] = color
            logger.debug(f"Extracted color: {color} from '{text}'")
            break

    for flavor in flavors:
        if re.search(r"\b" + re.escape(flavor) + r"\b", text_lower):
            result["variant_flavor"] = flavor
            logger.debug(f"Extracted flavor: {flavor} from '{text}'")
            break

    for type_variant in types:
        if re.search(r"\b" + re.escape(type_variant) + r"\b", text_lower):
            result["variant_type"] = type_variant
            logger.debug(f"Extracted type: {type_variant} from '{text}'")
            break

    return result


def parse_product_details(
    name: str,
    weight: str | None = None,
    volume: str | None = None,
    language: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    """Parse all product details from name, weight, and volume fields."""
    result: dict[str, Any] = {
        "amount_value": None,
        "amount_unit": None,
        "pack_quantity": 1,
        "variant_color": None,
        "variant_flavor": None,
        "variant_type": None,
    }

    # language param → country mapping → None (all languages)
    resolved_language = language
    if not resolved_language and country:
        country_map = _get_country_language_map()
        resolved_language = country_map.get(country.upper())
        if resolved_language:
            logger.debug(f"Resolved language '{resolved_language}' from country '{country}'")

    # Extract multi-pack info from name
    if name:
        pack_count, pack_amount, pack_unit = extract_pack_info(name)
        result["pack_quantity"] = pack_count

        if pack_amount and pack_unit:
            # Multi-pack with unit amount found (e.g., "6 x 330ml")
            result["amount_value"] = pack_amount
            result["amount_unit"] = pack_unit
            logger.debug(f"Using multi-pack amount: {pack_amount} {pack_unit}")

    # Try to extract from weight field (if no amount yet)
    if weight and (result["amount_value"] is None or result["amount_unit"] is None):
        # Normalize UN/CEFACT codes first
        weight_normalized = _normalize_un_cefact_in_text(weight)
        amount, unit = extract_amount_and_unit(weight_normalized)
        if amount and unit:
            result["amount_value"] = amount
            result["amount_unit"] = unit
            logger.debug(f"Using weight field amount: {amount} {unit}")

    # Try to extract from volume field (if no amount yet)
    if volume and (result["amount_value"] is None or result["amount_unit"] is None):
        # Normalize UN/CEFACT codes first
        volume_normalized = _normalize_un_cefact_in_text(volume)
        amount, unit = extract_amount_and_unit(volume_normalized)
        if amount and unit:
            result["amount_value"] = amount
            result["amount_unit"] = unit
            logger.debug(f"Using volume field amount: {amount} {unit}")

    # Fallback to extracting from name (if no amount yet)
    if name and (result["amount_value"] is None or result["amount_unit"] is None):
        amount, unit = extract_amount_and_unit(name)
        if amount and unit:
            result["amount_value"] = amount
            result["amount_unit"] = unit
            logger.debug(f"Using name field amount: {amount} {unit}")

    # Extract variants from name (language-aware)
    if name:
        variants = extract_variants(name, language=resolved_language)
        result.update(variants)

    logger.debug(f"Parsed product details: {result}")
    return result
