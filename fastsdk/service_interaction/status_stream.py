"""Socaity ``GET /stream`` subscription for the meseex ``Streaming`` task.

The gateway multiplexes named ``event: job`` status snapshots and unnamed output
on one response. This object owns that GET: job frames go to the wait task,
output records go to a push-fed ``StreamSession`` so ``job.stream()`` does not
open a second connection.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncIterator, Optional

from socaity_schemas.public.providers import SocaityJobResponse

from fastsdk.service_interaction.response.sse_records import aiter_sse_records
from fastsdk.service_interaction.response.stream_session import StreamSession

if TYPE_CHECKING:
    import httpx

    from fastsdk.service_interaction.request import APIClient


class StatusStream:
    """One ``GET /stream``; ``output`` is the session callers iterate."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.output = StreamSession(None, loop)
        self._response: Optional["httpx.Response"] = None

    async def snapshots(self, api_client: "APIClient", envelope: object) -> AsyncIterator[SocaityJobResponse]:
        """Open the stream and yield each ``event: job`` snapshot.

        Unnamed records are pushed to ``output``. The feed is ended when the
        response closes or this iterator is left.
        """
        error: Optional[BaseException] = None
        self._response = await api_client.open_stream(envelope)
        try:
            async for event, data in aiter_sse_records(self._response.aiter_lines()):
                if event == "job":
                    yield SocaityJobResponse.model_validate_json(data)
                elif event is None:
                    self.output.feed(data)
        except Exception as exc:
            error = exc
            raise
        finally:
            self.output.end(error)
            await self.aclose()

    def close(self) -> None:
        """End the output feed and close the HTTP response from any thread."""
        self.output.end()
        try:
            future = asyncio.run_coroutine_threadsafe(self.aclose(), self._loop)
            future.result(timeout=5)
        except Exception:
            pass

    async def aclose(self) -> None:
        """Close the HTTP response. Idempotent."""
        response = self._response
        self._response = None
        if response is None or response.is_closed:
            return
        try:
            await response.aclose()
        except Exception:
            pass
