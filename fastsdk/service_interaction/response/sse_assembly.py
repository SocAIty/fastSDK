"""Shared SSE stream parsing and result assembly for job streaming."""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

from media_toolkit import AudioFile, ImageFile, MediaFile, VideoFile, media_from_any

_BASE64_CHARSET = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def chunk_text(chunk: Any) -> str:
    """Extract text from an OpenAI-style SSE chunk, or stringify it."""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        choices = chunk.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or choices[0].get("message") or {}
            return delta.get("content") or ""
    return str(chunk)


def looks_like_base64(payload: bytes) -> bool:
    """Fast base64 shape check without decoding the full payload."""
    if not payload or len(payload) % 4:
        return False
    return all(byte in _BASE64_CHARSET for byte in payload)


def is_mostly_text(data: bytes) -> bool:
    if not data or b"\x00" in data:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for char in text if char.isprintable() or char in "\n\r\t")
    return printable / len(text) > 0.95


def bytes_to_result(data: bytes) -> Any:
    """Turn raw bytes into text, a typed media file, or an opaque byte payload."""
    if is_mostly_text(data):
        return data.decode("utf-8")
    try:
        media = media_from_any(data, allow_reads_from_disk=False)
        if isinstance(media, (VideoFile, ImageFile, AudioFile)):
            return media
        if isinstance(media, MediaFile):
            return data
        return media
    except Exception:
        return data


def assemble_sse_bytes(data: bytes) -> Optional[Any]:
    """Parse SSE-framed bytes; return None when the body is raw passthrough."""
    if not data:
        return ""

    json_payloads: list[bytes] = []
    binary_chunks: list[bytes] = []
    text_payloads: list[bytes] = []
    saw_data_line = False

    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(b":"):
            continue
        if not line.startswith(b"data:"):
            if saw_data_line:
                continue
            return None
        saw_data_line = True
        payload = line[5:].strip()
        if payload == b"[DONE]":
            continue
        if payload.startswith(b"{"):
            json_payloads.append(payload)
        elif looks_like_base64(payload):
            try:
                binary_chunks.append(base64.b64decode(payload))
            except Exception:
                text_payloads.append(payload)
        else:
            text_payloads.append(payload)

    if json_payloads:
        return "".join(
            chunk_text(json.loads(payload.decode("utf-8")))
            for payload in json_payloads
        )
    if binary_chunks:
        return bytes_to_result(b"".join(binary_chunks))
    if text_payloads:
        return b"".join(text_payloads).decode("utf-8", errors="replace")
    return ""


def assemble_stream_bytes(data: bytes, *, is_sse: bool) -> Any:
    """Assemble a full streaming response body into a single result value."""
    if is_sse:
        parsed = assemble_sse_bytes(data)
        if parsed is not None:
            return parsed
    return bytes_to_result(data)
