"""Shared SSE stream parsing and result assembly for job streaming."""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

from media_toolkit import AudioFile, ImageFile, MediaFile, VideoFile, media_from_any

from fastsdk.service_interaction.response.sse_records import iter_sse_records

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
    """Parse SSE-framed bytes; return None when the body is raw passthrough.

    Named records (``event: job``) and ``[DONE]`` carry no output and are skipped.
    """
    if not data:
        return ""

    lines = data.decode("utf-8", errors="replace").splitlines()
    first_field = next((line.strip() for line in lines if line.strip() and not line.startswith(":")), "")
    if not first_field.startswith(("data:", "event:")):
        return None

    json_payloads: list[str] = []
    binary_chunks: list[bytes] = []
    text_payloads: list[str] = []

    for event, payload in iter_sse_records(lines):
        if event or payload == "[DONE]":
            continue
        if payload.startswith("{"):
            json_payloads.append(payload)
        elif looks_like_base64(payload.encode()):
            try:
                binary_chunks.append(base64.b64decode(payload))
            except Exception:
                text_payloads.append(payload)
        else:
            text_payloads.append(payload)

    if json_payloads:
        return "".join(chunk_text(json.loads(payload)) for payload in json_payloads)
    if binary_chunks:
        return bytes_to_result(b"".join(binary_chunks))
    return "".join(text_payloads)


def assemble_stream_bytes(data: bytes, *, is_sse: bool) -> Any:
    """Assemble a full streaming response body into a single result value."""
    if is_sse:
        parsed = assemble_sse_bytes(data)
        if parsed is not None:
            return parsed
    return bytes_to_result(data)
