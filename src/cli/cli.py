import atexit
import logging
from pathlib import Path
import signal
import sys
from types import FrameType

from chalkbox.logging.bridge import setup_logging
import click

from src.cli.commands.database import db
from src.cli.commands.groups import groups
from src.cli.commands.refresh import refresh
from src.cli.commands.track import track
from src.config.config_loader import load_typed_config

_shutdown_requested = False

logger = logging.getLogger(__name__)


def _signal_handler(signum: int, _frame: FrameType | None) -> None:
    """Handle SIGINT (Ctrl+C) and SIGTERM gracefully."""
    global _shutdown_requested

    if _shutdown_requested:
        # Second signal (force exit)
        logger.warning("Force shutdown - terminating immediately")
        sys.exit(1)

    # First signal (request graceful shutdown)
    _shutdown_requested = True
    signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    logger.debug(f"Received {signal_name} - initiating graceful shutdown")
    logger.info("\nShutdown requested - completing current operations...")


def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    return _shutdown_requested


def _cleanup_on_exit():
    """Emergency cleanup handler called on program exit."""
    if _shutdown_requested:
        logger.debug("Emergency cleanup: shutdown was already requested")
    else:
        logger.debug("Emergency cleanup: normal exit")


@click.group(invoke_without_command=True)
@click.option(
    "--config",
    "-c",
    "config_file",
    type=click.Path(exists=True),
    help="Path to config file (default: config.yaml)",
)
@click.option(
    "--provider-config",
    "-pc",
    "provider_config",
    type=click.Path(),
    help="Override provider config file (e.g., store_a.minimal.yaml)",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging output (overrides config dev_mode)",
)
@click.version_option(version="1.0.0")
@click.pass_context
def cli(ctx: click.Context, config_file: Path | str, provider_config: str, debug: bool):
    """Price Scout - Modular browser automation toolkit for price monitoring."""
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file
    ctx.obj["provider_config"] = provider_config
    ctx.obj["debug"] = debug

    try:
        config = load_typed_config(config_path=config_file)
        dev_mode = config.cli.dev_mode
    except Exception:
        dev_mode = False

    if debug:
        # --debug flag: Full debug output with clean formatting
        setup_logging(
            level="DEBUG",
            show_time=False,
            show_level=False,
            show_path=False,
            rich_tracebacks=True,
        )
    elif dev_mode:
        # dev_mode: true - Developer output with technical details
        setup_logging(
            level="DEBUG",
            show_time=True,
            show_level=True,
            show_path=True,
            rich_tracebacks=True,
        )
    else:
        # dev_mode: false (default) - Clean user-friendly output
        setup_logging(
            level="WARNING",
            show_time=False,
            show_level=False,
            show_path=False,
            rich_tracebacks=False,
        )

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    logger.debug("Signal handlers registered for graceful shutdown")

    atexit.register(_cleanup_on_exit)
    logger.debug("Atexit cleanup handler registered")

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()


cli.add_command(groups)
cli.add_command(db)

cli.add_command(track)
cli.add_command(refresh)


if __name__ == "__main__":
    cli()
