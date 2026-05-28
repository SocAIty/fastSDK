"""Provider-aware response parsing via plain function dispatch.

Design:
  - One pure function per provider for JSON → model conversion.
  - One pure function per provider for media result post-processing.
  - ``ResponseParser`` is a thin dispatcher holding a provider string and
    two function references.
  - The Runpod-hosted-APIPod edge case is handled by *function composition*:
    ``_parse_runpod_apipod`` calls ``_parse_runpod`` then ``_parse_socaity``.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional, Union

import httpx
from media_toolkit import media_from_any

from fastsdk.service_interaction.response.response_schemas import (
    ReplicateJobResponse,
    RunpodJobResponse,
    SocaityJobResponse,
    StreamingResponse,
)

# ---------------------------------------------------------------------------
# Media helpers (pure, stateless)
# ---------------------------------------------------------------------------


def _parse_media_socaity(result: Any) -> Any:
    if result is None:
        return result
    if isinstance(result, (dict, list)):
        try:
            return media_from_any(result, allow_reads_from_disk=False)
        except Exception:
            return result
    return result


def _parse_media_replicate(result: Any) -> Any:
    if isinstance(result, str) and "https://replicate.delivery" in result:
        try:
            return media_from_any(result, allow_reads_from_disk=False)
        except Exception:
            return result
    if isinstance(result, list):
        return [_parse_media_replicate(item) for item in result]
    if isinstance(result, dict):
        return {k: _parse_media_replicate(v) for k, v in result.items()}
    return result


# ---------------------------------------------------------------------------
# JSON → model parse functions (pure, stateless)
# ---------------------------------------------------------------------------


def _parse_socaity(data: dict, parse_media: bool) -> Union[SocaityJobResponse, dict]:
    if "job_id" not in data:
        return data

    payload = dict(data)

    progress = payload.get("progress")
    if isinstance(progress, dict) and not payload.get("message"):
        payload["message"] = progress.get("message")

    if parse_media:
        payload["result"] = _parse_media_socaity(payload.get("result"))

    return SocaityJobResponse(**payload)


def _parse_runpod(data: dict, parse_media: bool) -> Union[RunpodJobResponse, dict]:
    if "id" not in data or "status" not in data:
        return data
    return RunpodJobResponse(**data)


def _parse_replicate(data: dict, parse_media: bool) -> Union[ReplicateJobResponse, dict]:
    urls = data.get("urls") or {}
    if "id" not in data or "get" not in urls:
        return data
    if parse_media:
        data = {**data, "output": _parse_media_replicate(data.get("output"))}
    return ReplicateJobResponse(**data)


def _try_unwrap_apipod(output: Any) -> Optional[dict]:
    """Try to extract a nested APIPod/Socaity payload from Runpod output."""
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(output, dict) and "job_id" in output:
        return output
    return None


def _parse_runpod_apipod(data: dict, parse_media: bool) -> Union[SocaityJobResponse, RunpodJobResponse, dict]:
    """Compose Runpod transport parsing with nested APIPod payload extraction.

    Returns SocaityJobResponse when a nested payload is found (subsequent
    polling/cancel use Socaity links), otherwise falls back to RunpodJobResponse.
    """
    if "id" not in data or "status" not in data:
        return data

    nested = _try_unwrap_apipod(data.get("output"))
    if nested:
        return _parse_socaity(nested, parse_media=parse_media)

    return RunpodJobResponse(**data)


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

_JSON_PARSERS: dict[str, Callable] = {
    "socaity": _parse_socaity,
    "apipod": _parse_socaity,
    "runpod": _parse_runpod,
    "replicate": _parse_replicate,
    "runpod_apipod": _parse_runpod_apipod,
}

_MEDIA_PARSERS: dict[str, Callable] = {
    "socaity": _parse_media_socaity,
    "apipod": _parse_media_socaity,
    "replicate": _parse_media_replicate,
    "runpod_apipod": _parse_media_socaity,
}


# ---------------------------------------------------------------------------
# ResponseParser — thin dispatcher
# ---------------------------------------------------------------------------


class ResponseParser:
    """Thin, stateless dispatcher. Holds a provider string and two function
    references looked up from the dispatch tables above."""

    __slots__ = ("provider", "_json_parser", "_media_parser")

    def __init__(self, provider: str):
        self.provider = provider
        self._json_parser = _JSON_PARSERS.get(provider)
        self._media_parser = _MEDIA_PARSERS.get(provider)

    async def parse_response(
        self, response: httpx.Response, parse_media: bool = True
    ) -> Union[SocaityJobResponse, RunpodJobResponse, ReplicateJobResponse, StreamingResponse, bytes, None, dict]:
        if not response:
            return None

        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            return StreamingResponse()

        try:
            if not response.is_closed:
                await response.aread()
        except Exception:
            pass

        if "application/json" not in content_type:
            return response.content

        try:
            data = response.json()
        except json.JSONDecodeError:
            return response.content

        if self._json_parser:
            return self._json_parser(data, parse_media)
        return data

    def parse_media(self, raw_result: Any) -> Any:
        """Apply provider-specific media processing to a raw result value."""
        if self._media_parser:
            return self._media_parser(raw_result)
        return raw_result

    @staticmethod
    async def check_response_status(response: httpx.Response) -> Optional[str]:
        if 200 <= response.status_code < 300:
            return None

        error_messages = {
            401: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            403: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            404: f"Endpoint {response.url} error: not found. Check the URL and API key.",
        }
        if response.status_code in error_messages:
            return error_messages[response.status_code]

        try:
            await response.aread()
        except Exception:
            pass
        return f"Endpoint {response.url} error: {response.content}."
