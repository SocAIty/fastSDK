"""Bridge a live async httpx response into sync (and async) iteration.

The httpx response is created and owned by meseex's event loop, which runs in a
dedicated background thread. Iterating it from the caller's thread directly would
touch the response from the wrong loop. ``StreamSession`` solves this with a
single-producer/single-consumer hand-off: a producer coroutine scheduled on the
meseex loop reads the response and pushes items into a thread-safe queue; the
caller drains that queue from any thread (``iter_*``) or any loop (``aiter_*``).
"""

from __future__ import annotations

import asyncio
import json
import queue
from typing import Any, AsyncIterator, Callable, Iterator, Optional

import httpx

from fastsdk.service_interaction.response.sse_assembly import chunk_text


class StreamSession:
    """One open streaming response, consumable exactly once.

    Args:
        response: An open httpx response (sent with ``stream=True``).
        loop: The asyncio loop that owns the response (meseex's background loop).
        parse_chunk: Optional callable applied to each decoded SSE JSON object.
        content_type: Override for the response content type (else read from headers).
    """

    _SENTINEL = object()

    def __init__(
        self,
        response: httpx.Response,
        loop: asyncio.AbstractEventLoop,
        parse_chunk: Optional[Callable[[Any], Any]] = None,
        content_type: Optional[str] = None,
    ):
        self._response = response
        self._loop = loop
        self._parse_chunk = parse_chunk
        self.content_type = content_type or response.headers.get("Content-Type", "")
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._started = False
        self._error: Optional[BaseException] = None

    @property
    def is_sse(self) -> bool:
        return "text/event-stream" in self.content_type

    @staticmethod
    def chunk_text(chunk: Any) -> str:
        """Extract text from a stream chunk (OpenAI SSE JSON or plain string)."""
        return chunk_text(chunk)

    # ------------------------------------------------------------------
    # Producer (runs on the meseex loop)
    # ------------------------------------------------------------------

    def _start(self, mode: str):
        if self._started:
            return
        self._started = True
        coro = self._produce_sse() if mode == "sse" else self._produce_bytes()
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _produce_bytes(self):
        try:
            async for chunk in self._response.aiter_bytes():
                if chunk:
                    self._queue.put(chunk)
        except BaseException as e:  # surface to the consumer thread
            self._error = e
        finally:
            await self._aclose()
            self._queue.put(self._SENTINEL)

    async def _produce_sse(self):
        try:
            async for line in self._response.aiter_lines():
                item = self._decode_sse_line(line)
                if item is _SKIP:
                    continue
                if item is _DONE:
                    break
                self._queue.put(item)
        except BaseException as e:
            self._error = e
        finally:
            await self._aclose()
            self._queue.put(self._SENTINEL)

    async def _aclose(self):
        try:
            if not self._response.is_closed:
                await self._response.aclose()
        except Exception:
            pass

    def close(self) -> None:
        """Close the underlying response from any thread. Idempotent.

        Used for stream teardown on cancel: schedules the close on the owning
        loop and waits briefly so the response is released before returning.
        """
        if self._response.is_closed:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._aclose(), self._loop)
            future.result(timeout=5)
        except Exception:
            pass

    def _decode_sse_line(self, line: str) -> Any:
        if not line:
            return _SKIP
        line = line.strip()
        if not line or line.startswith(":"):  # blank or comment/keep-alive
            return _SKIP
        if not line.startswith("data:"):
            return line
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            return _DONE
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return data
        if self._parse_chunk is not None:
            return self._parse_chunk(obj)
        return obj

    # ------------------------------------------------------------------
    # Consumer (sync, any thread)
    # ------------------------------------------------------------------

    def _drain(self) -> Iterator[Any]:
        while True:
            item = self._queue.get()
            if item is self._SENTINEL:
                if self._error is not None:
                    raise self._error
                return
            yield item

    def __iter__(self) -> Iterator[Any]:
        """Auto-select SSE chunks or raw bytes based on the content type."""
        return self.iter_chunks() if self.is_sse else self.iter_bytes()

    def iter_chunks(self) -> Iterator[Any]:
        """Yield decoded (optionally validated) SSE chunks."""
        self._start("sse")
        yield from self._drain()

    def iter_bytes(self) -> Iterator[bytes]:
        """Yield raw byte chunks of a binary stream."""
        self._start("bytes")
        yield from self._drain()

    # ------------------------------------------------------------------
    # Consumer (async, caller's loop)
    # ------------------------------------------------------------------

    async def _adrain(self) -> AsyncIterator[Any]:
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, self._queue.get)
            if item is self._SENTINEL:
                if self._error is not None:
                    raise self._error
                return
            yield item

    def __aiter__(self) -> AsyncIterator[Any]:
        """Auto-select SSE chunks or raw bytes based on the content type."""
        return self.aiter_chunks() if self.is_sse else self.aiter_bytes()

    async def aiter_chunks(self) -> AsyncIterator[Any]:
        self._start("sse")
        async for item in self._adrain():
            yield item

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        self._start("bytes")
        async for item in self._adrain():
            yield item


# Internal control markers for SSE line decoding.
_SKIP = object()
_DONE = object()
