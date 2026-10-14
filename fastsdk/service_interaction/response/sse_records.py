"""SSE helpers on top of ``httpx2.EventSource``.

The Socaity gateway multiplexes two record kinds on one response: named ``event: job``
status snapshots and unnamed ``data:`` output frames. Unnamed frames carry the SSE
default name ``message``; every reader filters on it so named records never leak
into token output.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx2

OUTPUT_EVENT = "message"

_SSE_HEADERS = {"content-type": "text/event-stream"}


def sse_events(response: httpx2.Response) -> httpx2.EventSource:
    """Event source without a per-event cap: media frames carry base64 bodies above httpx2's 1 MiB default."""
    return httpx2.EventSource(response, max_event_size=None)


def iter_buffered_events(data: bytes) -> Iterator[httpx2.ServerSentEvent]:
    """Decode a fully buffered SSE body with the same parser as live responses."""
    request = httpx2.Request("GET", "http://buffered.sse")
    return iter(sse_events(httpx2.Response(200, headers=_SSE_HEADERS, content=data, request=request)))


def decode_sse_data(data: str) -> Any:
    """Parse JSON payloads; plain text passes through."""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return data


def encode_sse_data(data: str) -> bytes:
    """Re-frame one unnamed record as SSE bytes."""
    return "".join(f"data: {line}\n" for line in data.split("\n")).encode("utf-8") + b"\n"
