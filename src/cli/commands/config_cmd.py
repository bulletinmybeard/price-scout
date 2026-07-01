from pathlib import Path

import click

from src.cli.chalkbox_helpers import show_error, show_info
from src.cli.helpers import get_console
from src.config.config_loader import (
    ConfigLoader,
    copy_bundled_provider_configs,
    ensure_user_directory,
    get_default_config_path,
    get_user_directory,
)

console = get_console()


@click.group()
def config():
    """Manage Price Scout configuration files."""
    pass


@config.command(name="init")
@click.option(
    "--path",
    "-p",
    "config_path",
    type=click.Path(),
    default=None,
    help="Config file path (default: environment-specific location)",
)
@click.option("--force", is_flag=True, help="Overwrite existing config file")
def config_init(config_path: str | None, force: bool):
    """Initialize config.yaml and provider configs for this environment."""
    try:
        target = Path(config_path) if config_path else get_default_config_path()

        if target.exists() and not force:
            show_info("Config already exists", details=str(target))
            console.print("[dim]Use --force to overwrite.[/dim]")
            return

        target.parent.mkdir(parents=True, exist_ok=True)

        loader = ConfigLoader(target)
        if not loader._create_default_config():
            show_error(
                "Failed to create config",
                details="Could not find bundled config.example.yaml",
            )
            raise click.Abort()

        if not ensure_user_directory():
            copy_bundled_provider_configs()

        show_info("Configuration initialized", details=str(target))
        if get_user_directory().exists():
            console.print(
                f"[dim]Provider configs: {get_user_directory() / 'provider_configs'}[/dim]"
            )
        console.print("[dim]Review and customize your config before tracking products.[/dim]")

    except click.Abort:
        raise
    except Exception as e:
        show_error("Config initialization failed", details=str(e))
        raise click.Abort() from e
