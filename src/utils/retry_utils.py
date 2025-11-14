import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from chalkbox.logging.bridge import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., Any],
    max_retries: int,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_errors: tuple[type[Exception], ...] = (Exception,),
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute an async function with exponential backoff retry logic."""
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Retry attempt {attempt} succeeded for {func.__name__}")
            return result

        except retryable_errors as e:
            last_exception = e
            if attempt >= max_retries:
                logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}: {e}")
                raise

            delay = initial_delay * (backoff_factor**attempt)
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
    raise RuntimeError(f"Retry logic failed unexpectedly for {func.__name__}")


def should_retry_on_result(
    result: Any,
    retry_condition: Callable[[Any], bool],
) -> bool:
    """Check if a result should trigger a retry based on custom condition."""
    return retry_condition(result)
