from rich.progress import ProgressColumn, Task
from rich.text import Text


class TaskCompletionTimeColumn(ProgressColumn):
    """Custom column that shows when each task completed (or -:--:-- if ongoing)."""

    def __init__(self, completion_times: dict):
        """Initialize with dict to track completion times by task ID."""
        super().__init__()
        self.completion_times = completion_times

    def render(self, task: Task) -> Text:
        """Render task completion time or -:--:-- if not finished."""
        if task.id in self.completion_times:
            elapsed_seconds = self.completion_times[task.id]
            hours = int(elapsed_seconds // 3600)
            minutes = int((elapsed_seconds % 3600) // 60)
            seconds = int(elapsed_seconds % 60)
            return Text(f"{hours}:{minutes:02d}:{seconds:02d}", style="cyan")
        else:
            return Text("-:--:--", style="cyan")


class CurrentProductColumn(ProgressColumn):
    """Custom column to show current product being processed with success/failure status."""

    def __init__(
        self,
        current_products: dict,
        spinner_frames: list,
        frame_index: list,
        success_counts: dict,
        failure_counts: dict,
    ):
        """Initialize with state dictionaries for tracking progress."""
        super().__init__()
        self.current_products = current_products
        self.spinner_frames = spinner_frames
        self.frame_index = frame_index
        self.success_counts = success_counts
        self.failure_counts = failure_counts

    def render(self, task: Task) -> Text:
        """Render current product with spinner or success/failure status."""
        provider_key = task.description.strip().lower().replace(" ", "_")

        current_product = self.current_products.get(provider_key, "")

        if task.completed == task.total and task.total > 0:
            failures = self.failure_counts.get(provider_key, 0)

            if failures == 0:
                return Text(" ✓", style="green")
            else:
                return Text(f" ✗{failures}", style="red")

        if current_product:
            self.frame_index[0] = (self.frame_index[0] + 1) % len(self.spinner_frames)
            spinner_char = self.spinner_frames[self.frame_index[0]]

            return Text(f" {spinner_char} {current_product}", style="dim cyan")

        return Text("")
