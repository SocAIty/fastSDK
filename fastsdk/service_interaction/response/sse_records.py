"""SSE wire format: fold ``text/event-stream`` lines into ``(event, data)`` records.

The Socaity gateway multiplexes two record kinds on one response: named ``event: job``
status snapshots and unnamed ``data:`` output frames. Every reader goes through this
parser so named records never leak into token output.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterable, AsyncIterator, Iterable, Iterator, Optional, Tuple

SseRecord = Tuple[Optional[str], str]


class SseRecordParser:
    """Accumulate lines; a blank line dispatches the record. Comments and ``id:`` are ignored."""

    def __init__(self) -> None:
        self._event: Optional[str] = None
        self._data: list[str] = []

    def feed(self, line: str) -> Optional[SseRecord]:
        line = line.rstrip("\r")
        if not line:
            return self.flush()
        if line.startswith("event:"):
            self._event = line[6:].strip()
        elif line.startswith("data:"):
            self._data.append(line[5:].strip())
        return None

    def flush(self) -> Optional[SseRecord]:
        record = (self._event or None, "\n".join(self._data)) if self._data else None
        self._event, self._data = None, []
        return record


def iter_sse_records(lines: Iterable[str]) -> Iterator[SseRecord]:
    parser = SseRecordParser()
    for line in lines:
        if record := parser.feed(line):
            yield record
    if record := parser.flush():
        yield record


async def aiter_sse_records(lines: AsyncIterable[str]) -> AsyncIterator[SseRecord]:
    parser = SseRecordParser()
    async for line in lines:
        if record := parser.feed(line):
            yield record
    if record := parser.flush():
        yield record


def decode_sse_data(data: str) -> Any:
    """Parse JSON payloads; plain text passes through."""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return data


def encode_sse_data(data: str) -> bytes:
    """Re-frame one unnamed record as SSE bytes."""
    return "".join(f"data: {line}\n" for line in data.split("\n")).encode("utf-8") + b"\n"
