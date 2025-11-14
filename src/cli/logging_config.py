from contextlib import contextmanager
import logging
from typing import Literal
import warnings


def configure_logging_for_output_mode(
    mode: Literal["debug", "json", "table"], debug_flag: bool = False
) -> None:
    """Configure logging levels based on CLI output mode.

    Logging Levels:
        - debug: Show all DEBUG and above logs
        - json: Suppress ALL logging (CRITICAL+1) and warnings
        - table: Show only WARNING and above (production-ready)
    """
    logger_names = ["src", "config", "playwright", "urllib3", "asyncio"]

    if mode == "debug" or debug_flag:
        # Debug mode: Show all DEBUG and above logs
        logging.getLogger().setLevel(logging.DEBUG)
        for logger_name in logger_names:
            logging.getLogger(logger_name).setLevel(logging.DEBUG)

    elif mode == "json":
        # Suppress ALL logging in JSON mode (above CRITICAL)
        logging.getLogger().setLevel(logging.CRITICAL + 1)
        warnings.filterwarnings("ignore")

        # Suppress all child loggers for clean JSON output
        for logger_name in logger_names:
            logging.getLogger(logger_name).setLevel(logging.CRITICAL + 1)

    else:  # table mode (default)
        # Show only WARNING and above in table mode (production-ready)
        logging.getLogger().setLevel(logging.WARNING)

        # Suppress child loggers for clean table output
        for logger_name in logger_names:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


@contextmanager
def suppress_loggers_during_rich_display():
    """Context manager to suppress all loggers during Rich Live display.

    Temporarily sets all loggers to CRITICAL level to prevent console output
    from breaking Rich progress bars and live displays. Restores previous
    levels on exit.
    """
    logger_names = [
        "",  # Root logger
        "src",
        "config",
        "playwright",
        "urllib3",
        "asyncio",
        "src.config",
        "src.providers",
        "src.scrapers",
    ]

    previous_log_levels = {}
    for logger_name in logger_names:
        temp_logger = logging.getLogger(logger_name)
        previous_log_levels[logger_name] = temp_logger.level
        temp_logger.setLevel(logging.CRITICAL)

    try:
        yield
    finally:
        # Restore previous levels
        for logger_name, level in previous_log_levels.items():
            logging.getLogger(logger_name).setLevel(level)
