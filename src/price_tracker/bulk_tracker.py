from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr
from io import StringIO
import sys
from threading import Lock
from typing import Any

from chalkbox.logging.bridge import get_logger
from rich.console import Group as RichGroup
from rich.live import Live
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.text import Text

from src.cli.helpers import (
    detect_provider_from_url,
    get_console,
    get_db_url,
    get_display_name_for_url,
)
from src.cli.logging_config import suppress_loggers_during_rich_display
from src.cli.progress_components import CurrentProductColumn
from src.database.db_manager import DatabaseManager
from src.price_tracker.scraping_worker import scrape_single_url

logger = get_logger(__name__)


class BulkTracker:
    """Orchestrator for tracking multiple URLs in parallel with progress display.

    This class handles the complex logic of:
    - Grouping URLs by provider
    - Setting up progress bars
    - Managing ThreadPoolExecutor for parallel execution
    - Displaying real-time progress
    - Handling keyboard interrupts gracefully
    - Aggregating and displaying results
    """

    def __init__(
        self,
        tracker,
        factory,
        db_manager: DatabaseManager,
        check: bool = False,
        cached: bool = False,
        json_output: bool = False,
    ):
        """Initialize bulk tracker."""
        self.tracker = tracker
        self.factory = factory
        self.db_manager = db_manager
        self.check = check
        self.cached = cached
        self.json_output = json_output

    def track_multiple_urls(
        self, urls: list[str], group_name: str | None = None
    ) -> list[tuple[str, str, Any]]:
        """Track multiple URLs in parallel with progress display."""
        results: list[tuple[str, str, Any]] = []
        urls_to_scrape = []

        # Check whether `--cached` exists and return the latest snapshot
        if self.cached:
            for url in urls:
                snapshot = self.db_manager.get_latest_snapshot(url)
                if snapshot:
                    results.append(("cached", url, snapshot))
                else:
                    urls_to_scrape.append(url)
        else:
            urls_to_scrape = urls.copy()

        if not urls_to_scrape:
            return results

        urls_by_provider = defaultdict(list)
        for url in urls_to_scrape:
            provider_name, _ = detect_provider_from_url(url, self.factory)
            provider_key = provider_name if provider_name else "unknown"
            urls_by_provider[provider_key].append(url)

        total_products = len(urls_to_scrape)
        total_providers = len(urls_by_provider)

        if self.json_output:
            # JSON mode: Simple parallel execution without progress bars
            return self._track_parallel_json_mode(urls_to_scrape, group_name, results)
        else:
            # Table mode: Full progress bar display
            return self._track_parallel_with_progress(
                urls_to_scrape,
                urls_by_provider,
                total_products,
                total_providers,
                group_name,
                results,
            )

    def _track_parallel_json_mode(
        self, urls_to_scrape: list[str], group_name: str | None, results: list
    ) -> list[tuple[str, str, Any]]:
        """Track URLs in parallel without progress bars (JSON mode)."""
        max_workers = max(1, min(len(urls_to_scrape), 3))
        db_url = get_db_url()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    scrape_single_url,
                    url,
                    self.tracker,
                    self.factory,
                    self.check,
                    db_url,
                    group_name,
                )
                for url in urls_to_scrape
            ]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        return results

    def _track_parallel_with_progress(
        self,
        urls_to_scrape: list[str],
        urls_by_provider: dict,
        total_products: int,
        total_providers: int,
        group_name: str | None,
        results: list,
    ) -> list[tuple[str, str, Any]]:
        """Track URLs in parallel with Rich progress bars (table mode)."""
        console = get_console()
        console.print(
            f"\nTracking {total_products} product(s) across {total_providers} provider(s)\n"
        )

        success_counts: dict = defaultdict(int)
        failure_counts: dict = defaultdict(int)
        failures_by_provider: dict = defaultdict(list)  # provider -> [(url, error_msg), ...]
        current_product_by_provider: dict = {}
        completed_by_provider: dict = defaultdict(int)
        interrupted = [False]

        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame_index = [0]

        update_lock = Lock()

        global_progress = Progress(
            TextColumn("[bold cyan][ Providers ][/bold cyan]"),
            BarColumn(complete_style="cyan", finished_style="cyan"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        )

        provider_progress = Progress(
            TextColumn("{task.description}", justify="left", style="dim"),
            BarColumn(complete_style="green", finished_style="green"),
            MofNCompleteColumn(),
            CurrentProductColumn(
                current_product_by_provider,
                spinner_frames,
                frame_index,
                success_counts,
                failure_counts,
            ),
        )

        global_task = global_progress.add_task("", total=total_products)

        provider_tasks = {}
        for provider_key, urls in urls_by_provider.items():
            provider_display = provider_key.replace("_", " ").title()
            task_id = provider_progress.add_task(f"  {provider_display:<15}", total=len(urls))
            provider_tasks[provider_key] = task_id
            current_product_by_provider[provider_key] = "Processing..."

        progress_group = RichGroup(
            global_progress,
            Text(""),  # Blank line
            provider_progress,
        )

        url_to_provider = {}
        for provider_key, urls in urls_by_provider.items():
            for url in urls:
                url_to_provider[url] = provider_key

        url_to_display_name = {}
        for url in urls_to_scrape:
            display_name = get_display_name_for_url(url, self.db_manager)
            url_to_display_name[url] = display_name

        stderr_suppressor = StringIO() if self.json_output else sys.stderr

        with (
            suppress_loggers_during_rich_display(),
            redirect_stderr(stderr_suppressor),
            Live(progress_group, refresh_per_second=4),
        ):
            try:
                total_completed = 0

                max_workers = max(1, min(len(urls_to_scrape), 3))
                db_url = get_db_url()

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_url = {
                        executor.submit(
                            scrape_single_url,
                            url,
                            self.tracker,
                            self.factory,
                            self.check,
                            db_url,
                            group_name,
                        ): url
                        for url in urls_to_scrape
                    }

                    try:
                        for future in as_completed(future_to_url):
                            url = future_to_url[future]
                            provider_key = url_to_provider[url]

                            with update_lock:
                                display_name = url_to_display_name[url]
                                current_product_by_provider[provider_key] = display_name

                            try:
                                result = future.result()

                                with update_lock:
                                    completed_by_provider[provider_key] += 1
                                    total_completed += 1

                                    global_progress.update(global_task, completed=total_completed)
                                    provider_progress.update(
                                        provider_tasks[provider_key],
                                        completed=completed_by_provider[provider_key],
                                    )

                                    if result[0] == "error":
                                        failure_counts[provider_key] += 1
                                        error_msg = (
                                            result[2] if len(result) > 2 else "Unknown error"
                                        )
                                        failures_by_provider[provider_key].append(
                                            (url, str(error_msg))
                                        )
                                    else:
                                        success_counts[provider_key] += 1

                                    results.append(result)

                            except Exception as e:
                                with update_lock:
                                    failure_counts[provider_key] += 1
                                    failures_by_provider[provider_key].append((url, str(e)))

                                    completed_by_provider[provider_key] += 1
                                    total_completed += 1

                                    global_progress.update(global_task, completed=total_completed)
                                    provider_progress.update(
                                        provider_tasks[provider_key],
                                        completed=completed_by_provider[provider_key],
                                    )

                                    results.append(("error", url, str(e)))

                    except KeyboardInterrupt:
                        # Graceful shutdown on Ctrl+C
                        logger.debug("Keyboard interrupt received - cancelling pending tasks")
                        for future in future_to_url:
                            future.cancel()
                        executor.shutdown(wait=True, cancel_futures=True)
                        raise

            except KeyboardInterrupt:
                # Caught KeyboardInterrupt - exit gracefully
                interrupted[0] = True
                logger.debug("Exiting track command after interrupt")

            finally:
                for provider_key in urls_by_provider:
                    current_product_by_provider[provider_key] = ""

        if interrupted[0]:
            console.print("\n[yellow]Tracking interrupted - completed operations saved[/yellow]\n")
            completed_count = len(results)
            if completed_count > 0:
                console.print(
                    f"Processed {completed_count} of {total_products} product(s) before interruption\n"
                )
            raise KeyboardInterrupt()

        self._display_issues_summary(failures_by_provider, failure_counts)

        return results

    @staticmethod
    def _display_issues_summary(failures_by_provider: dict, failure_counts: dict) -> None:
        """Display summary of failures grouped by provider."""
        total_failures = sum(failure_counts.values())
        if total_failures == 0:
            return

        console = get_console()
        console.print(f"\n⚠ Tracked with issues — {total_failures} failure(s)\n", style="yellow")
        console.print("[bold]Issues[/bold]")

        for provider_key, failures in failures_by_provider.items():
            if not failures:
                continue

            provider_display = provider_key.replace("_", " ").title()
            console.print(f"  {provider_display} ({len(failures)})")

            for url, error_msg in failures:
                console.print(f"    ✗ {url}", style="red")
                console.print(f"      {error_msg}", style="dim red")

        console.print()
