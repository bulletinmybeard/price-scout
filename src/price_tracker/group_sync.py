from typing import Any

from chalkbox.logging.bridge import get_logger

from src.cli.helpers import detect_provider_from_url
from src.config.models import AppConfig
from src.database.db_manager import DatabaseManager
from src.providers import get_factory

logger = get_logger(__name__)


class GroupSync:
    """Wrapper class for group synchronization functionality."""

    def __init__(self, db_manager: DatabaseManager, config: AppConfig):
        """Initialize GroupSync with database manager and typed config."""
        self.db_manager = db_manager
        self.config = config

    def sync_groups(self, dry_run: bool = False) -> dict[str, list[str]]:
        """Sync groups from config to database."""
        changes: dict[str, list[str]] = {"created": [], "updated": [], "deactivated": []}

        config_groups = {g.name: g for g in self.config.product_groups}
        db_groups = {g["name"]: g for g in self.db_manager.get_all_groups()}

        for group_name in config_groups.keys() - db_groups.keys():
            changes["created"].append(group_name)
            if not dry_run:
                group_config = config_groups[group_name]
                group_id = self.db_manager.create_group(
                    name=group_name, description=group_config.description
                )

                factory = get_factory()

                for page in group_config.pages:
                    # Handle both string URLs and ProductGroupPageConfig
                    url = page.url if hasattr(page, "url") else page
                    provider_name, _ = detect_provider_from_url(url, factory)
                    if not provider_name:
                        logger.warning(f"Could not detect provider for URL: {url}")
                        continue

                    page_data = {
                        "url": url,
                        "provider": provider_name,
                        "enabled": True,
                    }
                    page_id = self.db_manager.add_tracked_page(page_data)
                    self.db_manager.add_page_to_group(page_id=page_id, group_id=group_id)

        for group_name in config_groups.keys() & db_groups.keys():
            config_group = config_groups[group_name]
            db_group = db_groups[group_name]

            if config_group.description != db_group.get("description", ""):
                changes["updated"].append(group_name)
                if not dry_run:
                    pass

        return changes


def sync_groups_from_config(
    config: AppConfig,
    db_manager: DatabaseManager,
    remove_orphans: bool = False,
) -> dict[str, Any]:
    """Sync product groups from config to database."""
    logger.debug("Starting group sync from config")

    stats: dict[str, Any] = {
        "groups_created": 0,
        "groups_updated": 0,
        "pages_added": 0,
        "pages_linked": 0,
        "errors": [],
    }

    groups = config.product_groups

    if not groups:
        logger.debug("No product groups defined in config")
        return stats

    logger.debug(f"Found {len(groups)} group(s) in config")

    config_associations = set()  # Set of (page_id, group_id) tuples

    for group_config in groups:
        group_name = group_config.name
        description = group_config.description
        pages = group_config.pages

        category = group_config.category
        weekly_usage = None
        meal_type = None
        tags: list[str] = []

        try:
            group_id = db_manager.create_group(
                name=group_name,
                description=description,
                category=category,
                weekly_usage=weekly_usage,
                meal_type=meal_type,
                tags=tags,
            )

            existing_group = db_manager.get_group_by_name(group_name)
            if existing_group and existing_group["description"] != description:
                stats["groups_updated"] += 1
            elif not existing_group:
                stats["groups_created"] += 1

            logger.debug(f"Processing group '{group_name}' (ID: {group_id})")

            factory = get_factory()
            for page in pages:
                url = page.url if hasattr(page, "url") else page
                provider_name = page.provider if hasattr(page, "provider") else None

                if not provider_name:
                    provider_name, _ = detect_provider_from_url(url, factory)
                    if not provider_name:
                        logger.warning(f"Could not detect provider for URL: {url}")
                        continue

                try:
                    page_data = {
                        "url": url,
                        "provider": provider_name,
                        "enabled": True,
                        "last_checked": None,
                        "last_price": None,
                    }

                    page_id = db_manager.add_tracked_page(page_data)

                    existing_page = db_manager.get_tracked_page(url)
                    if existing_page and existing_page["id"] == page_id:
                        stats["pages_added"] += 1

                    db_manager.add_page_to_group(page_id=page_id, group_id=group_id)
                    stats["pages_linked"] += 1

                    config_associations.add((page_id, group_id))

                    logger.debug(f"  ✓ Linked page {page_id} to group '{group_name}'")

                except Exception as e:
                    error_msg = f"Failed to process page {url} in group '{group_name}': {e}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Failed to process group '{group_name}': {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)

    logger.debug("Group sync completed:")
    logger.debug(f"  - Groups created: {stats['groups_created']}")
    logger.debug(f"  - Groups updated: {stats['groups_updated']}")
    logger.debug(f"  - Pages added: {stats['pages_added']}")
    logger.debug(f"  - Page-group links: {stats['pages_linked']}")

    if stats["errors"]:
        logger.warning(f"  - Errors: {len(stats['errors'])}")

    return stats


def sync_single_group(
    group_name: str,
    config: AppConfig,
    db_manager: DatabaseManager,
) -> bool:
    """Sync a single group from config to database."""
    group_config = next((g for g in config.product_groups if g.name == group_name), None)

    if not group_config:
        logger.error(f"Group '{group_name}' not found in config.yaml")
        return False

    logger.debug(f"Syncing group '{group_name}'...")

    try:
        group_id = db_manager.create_group(
            name=group_name,
            description=group_config.description,
            category=group_config.category,
        )

        factory = get_factory()
        for page in group_config.pages:
            url = page.url if hasattr(page, "url") else page
            provider_name = page.provider if hasattr(page, "provider") else None

            if not provider_name:
                provider_name, _ = detect_provider_from_url(url, factory)
                if not provider_name:
                    logger.warning(f"Could not detect provider for URL: {url}")
                    continue

            page_data = {
                "url": url,
                "provider": provider_name,
                "enabled": True,
            }

            page_id = db_manager.add_tracked_page(page_data)
            db_manager.add_page_to_group(page_id=page_id, group_id=group_id)

            logger.debug(f"  ✓ Linked {provider_name}: {url}")

        logger.debug(f"✓ Successfully synced group '{group_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to sync group '{group_name}': {e}")
        return False


def get_sync_status(
    config: AppConfig,
    db_manager: DatabaseManager,
) -> dict[str, Any]:
    """Get the current sync status between config and database."""
    config_groups = {g.name for g in config.product_groups}
    db_groups = {g["name"] for g in db_manager.get_all_groups()}

    in_sync = config_groups & db_groups
    missing_in_db = config_groups - db_groups
    extra_in_db = db_groups - config_groups

    return {
        "total_groups_config": len(config_groups),
        "total_groups_db": len(db_groups),
        "groups_in_sync": sorted(in_sync),
        "groups_missing_in_db": sorted(missing_in_db),
        "groups_extra_in_db": sorted(extra_in_db),
    }
