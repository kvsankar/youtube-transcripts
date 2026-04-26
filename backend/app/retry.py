"""Tiny retry helper for async work.

Used to make claude-CLI calls resilient to transient API errors and
process hangs. Deliberately small — no library dep.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)


async def with_retry(
    label: str,
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (30.0, 90.0),
    on_retry: Optional[Callable[[int, int], None]] = None,
) -> T:
    """Run `fn`, retrying on any exception up to `attempts` times.

    `backoff_seconds[i]` is how long to wait before attempt `i+2` (the
    first retry). The last value is reused if `attempts` exceeds the
    list length.

    `on_retry(next_attempt, total)` fires once before each retry — used
    to surface retry context in the UI.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            if attempt >= attempts:
                log.error("%s failed after %d attempts: %s", label, attempt, exc)
                raise
            wait_idx = min(attempt - 1, len(backoff_seconds) - 1)
            wait = backoff_seconds[wait_idx]
            log.warning(
                "%s attempt %d/%d failed: %s. Retrying in %.0fs.",
                label, attempt, attempts, exc, wait,
            )
            if on_retry:
                on_retry(attempt + 1, attempts)
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")  # for type checkers
