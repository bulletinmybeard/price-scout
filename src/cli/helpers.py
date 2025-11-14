import os
import re
from typing import Any
from urllib.parse import urlparse

from chalkbox import Console
from chalkbox.logging.bridge import get_logger
import click

from src.config.config_loader import (
    get_user_directory,
    is_development_environment,
    is_docker_environment,
    load_typed_config,
)
from src.database.db_manager import DatabaseManager
from src.utils.fuzzy_matcher import format_similarity_percentage

logger = get_logger(__name__)


def get_console(force_colors: bool | None = None) -> Console:
    """Get Console instance with proper color detection for Docker environments."""
    if force_colors is None:
        # Check FORCE_COLOR environment variable (set by Docker wrapper)
        force_colors = bool(os.getenv("FORCE_COLOR", ""))

    return Console(force_terminal=force_colors) if force_colors else Console()


def get_db_url(config_path: str | None = None) -> str:
    """
    Get database URL from config using type-safe Pydantic models.

    Default behavior when database.url is empty:
    - DOCKER CONTAINER: /data/price_scout.duckdb
    - LOCAL DEVELOPMENT: ./price_scout.duckdb (project root)
    - GLOBAL INSTALL: ~/.price-scout/database.duckdb

    This prevents creating home directory files during local poetry development.
    """
    config = load_typed_config(config_path)
    db_url = config.database.url

    if not db_url:
        # Docker environment: use container data volume
        if is_docker_environment():
            db_url = "/data/price_scout.duckdb"
        # Development: use project root database
        elif is_development_environment():
            db_url = "./price_scout.duckdb"
        # Global install: use user directory
        else:
            user_dir = get_user_directory()
            user_dir.mkdir(parents=True, exist_ok=True)
            db_url = str(user_dir / "database.duckdb")

    return db_url


def extract_amount_from_name(product_name: str) -> str | None:
    """
    Extract weight/volume/quantity from product name using regex patterns.

    .. deprecated:: 1.1.0
        Use :func:`src.utils.product_parser.parse_product_details` instead.
        This function is kept for backward compatibility but will be removed in v2.0.
        The new parser provides better extraction (multi-pack, variants, UN/CEFACT codes).

    Patterns matched:
        - "2 kg", "2kg", "2 kilo", "2kilo"
        - "1.5 l", "1.5l", "1.5 liter", "1,5 l"
        - "500 g", "500g", "500 gram"
        - "250 ml", "250ml", "250 milliliter"
        - "100 cl", "100cl", "100 centiliter"
        - "6 stuks", "6 st", "6x", "6-pack"
    """
    import warnings

    warnings.warn(
        "extract_amount_from_name() is deprecated and will be removed in v2.0. "
        "Use src.utils.product_parser.parse_product_details() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    if not product_name:
        return None

    # Patterns for common units (Tested with Dutch and German retailers)
    patterns = [
        # Weight: kg, kilo, gram, g (including KG, G, etc.)
        r"(\d+[,.]?\d*)\s*(kg|kilo|kilogram)",
        r"(\d+[,.]?\d*)\s*(g|gram)",
        # Volume: liter, l, ml, cl (including L, ML, CL, etc.)
        r"(\d+[,.]?\d*)\s*(l|liter)",
        r"(\d+[,.]?\d*)\s*(ml|milliliter)",
        r"(\d+[,.]?\d*)\s*(cl|centiliter)",
        # Pack/pieces: stuks, st, pack, x
        r"(\d+)\s*(stuks|stuk|st)",
        r"(\d+)\s*x",
        r"(\d+)[-\s]*pack",
    ]

    for pattern in patterns:
        match = re.search(pattern, product_name, re.IGNORECASE)
        if match:
            amount = match.group(1).replace(",", ".")
            unit = match.group(2) if len(match.groups()) > 1 else "x"

            unit_map = {
                "kilo": "kg",
                "kilogram": "kg",
                "gram": "g",
                "liter": "l",
                "milliliter": "ml",
                "centiliter": "cl",
                "stuks": "st",
                "stuk": "st",
                "pack": "x",
            }
            normalized_unit = unit_map.get(unit.lower(), unit.lower())

            return f"{amount} {normalized_unit}"

    return None


def detect_provider_from_url(url: str, factory) -> tuple[str | None, dict[str, Any] | None]:
    """Detect provider name from URL by matching scheme+host against base_url configs."""
    parsed_url = urlparse(url)
    url_base = f"{parsed_url.scheme}://{parsed_url.netloc}".lower()

    for provider_name, provider_config in factory.config.items():
        # provider_config is now a ProviderConfig Pydantic model, use attribute access
        base_url = provider_config.base_url.lower() if provider_config.base_url else ""

        if not base_url:
            continue

        if url_base == base_url:
            return provider_name, provider_config

        if url.lower().startswith(base_url):
            return provider_name, provider_config

    return None, None


def prompt_group_selection(
    input_name: str, similar_groups: list[tuple[dict[str, Any], float]], json_output: bool = False
) -> dict[str, Any] | None:
    """Interactively prompt user to select from similar groups or create new one.

    Shows similar groups with similarity percentages and lets user choose:
    - Select an existing group (1-N)
    - Create new group with input name (N+1)
    - Cancel operation (N+2)

    If there's a 100% exact match, automatically selects it without prompting.
    """
    if not similar_groups:
        return {"name": input_name, "is_new": True}

    # Check for 100% exact match - if found, use it automatically
    exact_match = next((group for group, similarity in similar_groups if similarity == 1.0), None)
    if exact_match:
        if not json_output:  # Only print in non-JSON mode
            console = get_console()
            console.print(
                f'[green]✓ Found exact match - using group "{exact_match["name"]}"[/green]'
            )
        return exact_match

    console = get_console()
    console.print("\n[yellow]Similar groups found:[/yellow]")

    for idx, (group, similarity) in enumerate(similar_groups, start=1):
        percentage = format_similarity_percentage(similarity)
        console.print(f"  {idx}. {group['name']} ({percentage} match)")

    create_option = len(similar_groups) + 1
    skip_option = create_option + 1
    cancel_option = skip_option + 1

    console.print(f'  {create_option}. Create new group "{input_name}" anyway')
    console.print(f"  {skip_option}. Skip group assignment (track without group)")
    console.print(f"  {cancel_option}. Cancel")

    while True:
        try:
            choice = click.prompt(
                f"\nSelect an option (1-{cancel_option})",
                type=int,
                show_default=False,
            )

            if 1 <= choice <= len(similar_groups):
                selected_group, _ = similar_groups[choice - 1]
                console.print(f'[green]✓ Using existing group "{selected_group["name"]}"[/green]')
                return selected_group

            elif choice == create_option:
                console.print(f'[blue]Creating new group "{input_name}"[/blue]')
                return {"name": input_name, "is_new": True}

            elif choice == skip_option:
                console.print("[yellow]Skipping group assignment - tracking without group[/yellow]")
                return {"skip": True}

            elif choice == cancel_option:
                console.print("[blue]Cancelled[/blue]")
                return None

            else:
                console.print(f"[red]Invalid choice. Please select 1-{cancel_option}[/red]")

        except (ValueError, click.Abort):
            console.print("[red]Invalid input. Please enter a number.[/red]")
        except KeyboardInterrupt:
            console.print("\n[blue]Cancelled[/blue]")
            return None


def get_display_name_for_url(url: str, db_manager: DatabaseManager) -> str:
    """Get display name for URL in progress displays.

    Priority:
    1. Product name from latest snapshot if URL was tracked
    2. Last segment of URL path
    3. Full URL as fallback

    Args:
        url: Product URL to get display name for
        db_manager: Database manager instance

    Returns:
        Display-friendly name for the URL
    """
    try:
        snapshot = db_manager.get_latest_snapshot(url)
        if snapshot and snapshot.get("name"):
            return snapshot["name"]
    except Exception as e:
        logger.debug(f"Failed to get product name from DB: {e}")

    try:
        path = urlparse(url).path
        segments = [s for s in path.split("/") if s]
        if segments:
            return segments[-1]
    except Exception as e:
        logger.debug(f"Failed to extract URL segment: {e}")

    return url
