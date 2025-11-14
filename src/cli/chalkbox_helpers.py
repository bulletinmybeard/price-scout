from datetime import datetime
from typing import Literal

from chalkbox import Alert, StatusCard, Stepper, get_console

console = get_console()


def show_error(message: str, details: str | None = None) -> None:
    """Display error alert with consistent styling."""
    console.print(Alert.error(message, details=details))


def show_success(message: str, details: str | None = None) -> None:
    """Display success alert with consistent styling."""
    console.print(Alert.success(message, details=details))


def show_warning(message: str, details: str | None = None) -> None:
    """Display warning alert with consistent styling."""
    console.print(Alert.warning(message, details=details))


def show_info(message: str, details: str | None = None) -> None:
    """Display info alert with consistent styling."""
    console.print(Alert.info(message, details=details))


def show_database_health(
    db_url: str,
    size_mb: float,
    page_snapshots: int,
    tracked_pages: int,
    product_groups: int,
    providers: int,
    oldest_snapshot: str | None = None,
    latest_snapshot: str | None = None,
) -> None:
    """Display database health status card with metrics and bars."""
    health_status: Literal["healthy", "warning", "error", "unknown"] = "healthy"
    if page_snapshots == 0:
        health_status = "warning"
    elif size_mb > 500:
        health_status = "warning"  # Large database

    avg_snapshots_per_page = page_snapshots / tracked_pages if tracked_pages > 0 else 0

    card = StatusCard(
        title="Database Health",
        status=health_status,
        subtitle=f"{db_url}",
        metrics={
            "Size": f"{size_mb:.2f} MB",
            "Product Snapshots": f"{page_snapshots:,}",
            "Tracked Pages": f"{tracked_pages:,}",
            "Product Groups": f"{product_groups:,}",
            "Unique Providers": f"{providers:,}",
            "Avg Snapshots": f"{avg_snapshots_per_page:.1f}",
        },
        bars=[
            ("Disk Usage", size_mb, 1000.0),  # Max 1GB
            ("Data Density", avg_snapshots_per_page, 100.0),
        ],
        bar_thresholds={
            "Disk Usage": (700.0, 900.0),  # Warning at 700MB, error at 900MB
            "Data Density": (50.0, 80.0),  # Warning/error for snapshot density
        },
    )

    console.print(card)

    if oldest_snapshot and latest_snapshot:
        try:
            oldest = datetime.fromisoformat(oldest_snapshot.replace("Z", "+00:00"))
            latest = datetime.fromisoformat(latest_snapshot.replace("Z", "+00:00"))
            time_span = (latest - oldest).days

            date_info = StatusCard(
                title="Data Timeline",
                status="healthy",
                metrics={
                    "Oldest Snapshot": oldest.strftime("%Y-%m-%d %H:%M:%S"),
                    "Latest Snapshot": latest.strftime("%Y-%m-%d %H:%M:%S"),
                    "Time Span": f"{time_span} days",
                },
            )
            console.print(date_info)
        except (ValueError, AttributeError):
            pass

    if page_snapshots == 0:
        console.print(
            Alert.info(
                "Database is empty",
                details="Start tracking products with: price-scout track --url <URL>",
            )
        )
    elif size_mb > 500:
        console.print(
            Alert.warning(
                "Large database detected",
                details="Consider archiving old snapshots or optimizing queries",
            )
        )


def create_workflow_stepper(
    steps: list[str | tuple[str, str]], title: str = "Workflow", show_numbers: bool = True
) -> Stepper:
    """Create stepper with predefined steps."""
    stepper = Stepper(title=title, show_numbers=show_numbers, live=False)

    for step in steps:
        if isinstance(step, tuple):
            name, description = step
            stepper.add_step(name, description)
        else:
            stepper.add_step(step)

    return stepper
