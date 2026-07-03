"""Single async->sync bridge over the meseex event loop.

The meseex task executor owns one asyncio loop in a background thread. Every
httpx response in fastsdk is created on that loop, so any follow-up coroutine
(poll, cancel, open stream, close) must run on the same loop. ``AsyncBridge`` is
the only place that crosses the sync/async boundary: it schedules a coroutine on
the loop and blocks on a ``concurrent.futures.Future`` with a timeout. Runtime
logic stays free of sleep/busy-wait loops.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Awaitable, Callable


class AsyncBridge:
    """Run coroutines on the meseex loop and block for their result.

    Args:
        async_executor: meseex ``AsyncTaskExecutor`` that owns the background loop.
    """

    def __init__(self, async_executor):
        self._async_executor = async_executor

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The running meseex loop. Owns every httpx response fastsdk creates."""
        self._async_executor._ensure_event_loop_running()
        return self._async_executor.loop

    def run(self, coro_func: Callable[..., Awaitable[Any]], *args, timeout_s: float = 30.0) -> Any:
        """Call an async function on the loop and block until it returns.

        Args:
            coro_func: Async callable to invoke on the loop.
            *args: Positional arguments forwarded to ``coro_func``.
            timeout_s: Max seconds to wait before cancelling and raising.
        """
        future = asyncio.run_coroutine_threadsafe(coro_func(*args), self.loop)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError("Timed out while waiting for async call")
