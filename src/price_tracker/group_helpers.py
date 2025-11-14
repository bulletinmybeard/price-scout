from chalkbox.logging.bridge import get_logger
import click

from src.cli.helpers import prompt_group_selection
from src.config.config_loader import load_typed_config
from src.database.db_manager import DatabaseManager
from src.utils.fuzzy_matcher import find_similar_groups

logger = get_logger(__name__)


def handle_fuzzy_group_matching(
    group_name: str | None, db_manager: DatabaseManager, json_output: bool = False
) -> str | None:
    """Handle fuzzy matching for group names with user interaction."""
    if not group_name:
        return None

    existing_groups = db_manager.get_all_groups_for_fuzzy_match()

    if not existing_groups:
        return group_name

    similar_groups = find_similar_groups(group_name, existing_groups, threshold=0.8, limit=3)

    if not similar_groups:
        return group_name

    selected = prompt_group_selection(group_name, similar_groups, json_output=json_output)

    if selected is None:
        if json_output:
            click.echo(
                click.style(
                    '{"status": "cancelled", "reason": "User cancelled group selection"}',
                    fg="yellow",
                )
            )
        else:
            click.echo("Cancelled")
        raise click.Abort()

    if selected.get("skip"):
        return None

    return selected["name"]


def auto_associate_with_groups(
    url: str, db_manager: DatabaseManager, config_path: str | None = None
) -> list[str]:
    """Automatically associate a tracked URL with product groups from config."""
    try:
        config = load_typed_config(config_path)
        product_groups = config.product_groups

        if not product_groups:
            return []

        associated_groups = []

        for group_config in product_groups:
            group_name = group_config.name
            if not group_name:
                continue

            pages = group_config.pages

            group_urls = []
            for page in pages:
                if isinstance(page, str):
                    group_urls.append(page)
                else:
                    group_urls.append(page.url)

            if url in group_urls:
                logger.debug(f"Found URL in group '{group_name}'")

                group_id = db_manager.create_group(
                    name=group_name, description=group_config.description
                )

                tracked_page = db_manager.get_tracked_page(url)
                if tracked_page:
                    db_manager.add_page_to_group(page_id=tracked_page["id"], group_id=group_id)
                    associated_groups.append(group_name)
                    logger.debug(f"Associated URL with group '{group_name}'")

        return associated_groups

    except Exception as e:
        logger.warning(f"Failed to auto-associate URL with groups: {e}")
        return []


def associate_tracked_page_with_group(
    url: str, group_name: str, db_manager: DatabaseManager
) -> bool:
    """Create group if needed and associate tracked page with it."""
    try:
        group_id = db_manager.create_group(name=group_name)

        tracked_page = db_manager.get_tracked_page(url)
        if not tracked_page:
            logger.warning(f"Tracked page not found for URL: {url}")
            return False

        db_manager.add_page_to_group(page_id=tracked_page["id"], group_id=group_id)
        logger.debug(f"Associated URL with group '{group_name}'")
        return True

    except Exception as e:
        logger.warning(f"Failed to associate with group '{group_name}': {e}")
        return False
