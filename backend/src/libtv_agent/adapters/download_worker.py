"""Keep blocking download threads from publishing after their caller exits."""

import asyncio
from collections.abc import Callable
from pathlib import Path


async def stage_download(
    worker: Callable[[], int], temporary: Path, destination: Path, *, timeout: float  # noqa: ASYNC109
) -> int:
    task = asyncio.create_task(asyncio.to_thread(worker))
    try:
        size = await asyncio.wait_for(asyncio.shield(task), timeout)
    except BaseException:
        # Thread cancellation is not supported. Drain before freeing its staging path.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if task.done() and not task.cancelled():
            task.exception()
        temporary.unlink(missing_ok=True)  # noqa: ASYNC240
        raise
    # Keep publication synchronous: no cancellation point between completion and rename.
    temporary.replace(destination)  # noqa: ASYNC240
    return size
