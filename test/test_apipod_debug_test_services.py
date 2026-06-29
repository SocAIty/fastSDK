"""
Integration tests for the APIPod debug test services (``apipod/test/debug_test_services.py``).

Exercises core, schema and streaming service groups against a locally running APIPod
instance. Launch whichever configuration you need, then point fastSDK at it:

    cd ../apipod && venv/Scripts/python test/debug_test_services.py   # apipod venv, default :8000
    apipod simulate serverless                           # job queue emulation
    apipod simulate dedicated                            # sync dedicated compute
    apipod simulate serverless-runpod                    # RunPod routing emulation

Run ``debug_test_services.py`` with the **apipod** project venv, not fastsdk's.
Use fastsdk's venv only for ``test_apipod_debug_test_services.py``.

Set ``APIPOD_DEBUG_TEST_SERVICE_URL`` when the service listens elsewhere.
``specification="apipod"`` keeps job polling correct for queue-backed launch modes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Optional

import pytest

import fastsdk
from socaity_schemas.service_definitions import (
    EndpointDefinition,
    EndpointParameter,
    ParameterDefinition,
    ServiceDefinition,
)
from media_toolkit import MediaFile, VideoFile

from fastsdk.service_interaction.response.sse_assembly import assemble_stream_bytes, chunk_text

DEFAULT_SERVICE_URL = "http://localhost:8000"
SERVICE_URL = os.environ.get("APIPOD_DEBUG_TEST_SERVICE_URL", DEFAULT_SERVICE_URL)
TEST_FILES_DIR = Path(__file__).resolve().parent / "test_files"
JOB_TIMEOUT_S = 120.0

# Mirrors apipod/test/services/streaming_service.py (stable contract for assertions).
TEXT_TOKENS = ["APIPod ", "streams ", "tokens ", "one ", "by ", "one."]
CHAT_TOKENS = ["Hello", ", ", "world", "!"]
VIDEO_FRAMES = [bytes([index]) * 2048 for index in range(5)]

MEDIA_RETURN_PATH_MARKERS = (
    "image-generation-",
    "video-generation-",
    "speech-",
    "/echo-image",
)


def _is_native_runpod_gateway(service_def: ServiceDefinition) -> bool:
    """True when the service exposes RunPod's generic /run API (APIPOD_NATIVE=true)."""
    paths = {endpoint.path for endpoint in service_def.endpoints}
    return "/run" in paths and not any("/core/" in path for path in paths)


def _service_def() -> ServiceDefinition:
    service_def = fastsdk.inspect_service(SERVICE_URL)
    if _is_native_runpod_gateway(service_def):
        pytest.skip(
            "Native RunPod local API (APIPOD_NATIVE=true) exposes only /run. "
            "Run the suite with serverless-runpod without APIPOD_NATIVE, or plain/serverless modes."
        )
    return service_def


def _client():
    api_key = os.environ.get("APIPOD_DEBUG_TEST_SERVICE_API_KEY")
    return fastsdk.connect(SERVICE_URL, api_key=api_key, specification="apipod")


def _test_files() -> dict[str, str]:
    return {
        "image": str(TEST_FILES_DIR / "test_face_1.jpg"),
        "audio": str(TEST_FILES_DIR / "test_audio.wav"),
        "video": str(TEST_FILES_DIR / "test_video_short.mp4"),
    }


def _definitions(param: EndpointParameter) -> list[ParameterDefinition]:
    definition = param.definition
    if definition is None:
        return []
    if isinstance(definition, list):
        return definition
    return [definition]


def _fake_value(param: EndpointParameter, files: dict[str, str]) -> Any:
    name = param.name.lower()
    if name == "messages":
        return [{"role": "user", "content": "hi"}]
    if name in {"prompt", "input", "text", "fries_name", "astring"}:
        return "test"
    if name in {"count", "anint", "anint2", "times", "amount", "n", "max_tokens"}:
        return 2
    if name in {"ratio"}:
        return 1.5
    if name in {"flag"}:
        return True
    if name in {"order", "a_base_model"}:
        return {"pam1": "test", "pam2": 2}
    if name in {"persona"}:
        return "pirate"

    if param.default is not None:
        return param.default

    for definition in _definitions(param):
        fmt = getattr(definition, "format", None)
        if fmt == "image":
            return files["image"]
        if fmt == "video":
            return files["video"]
        if fmt == "audio":
            return files["audio"]
        if fmt == "file":
            return files["image"]

        param_type = getattr(definition, "type", "string")
        if param_type == "integer":
            return 2
        if param_type == "number":
            return 1.5
        if param_type == "boolean":
            return False
        if param_type == "array":
            if fmt == "image":
                return [files["image"]]
            if fmt in {"video", "audio", "file"}:
                return [files.get(fmt, files["image"])]
            if fmt in {"binary", "string"}:
                return [files["image"]]
            return []
        if param_type == "object":
            return {"pam1": "test", "pam2": 2}

    return "test"


_FILE_FORMATS = frozenset({"file", "image", "video", "audio"})


def _param_has_file_format(param: EndpointParameter) -> bool:
    for definition in _definitions(param):
        if getattr(definition, "format", None) in _FILE_FORMATS:
            return True
    return False


def _kwargs_for_endpoint(endpoint: EndpointDefinition, files: dict[str, str]) -> dict[str, Any]:
    kwargs = {}
    for param in endpoint.parameters:
        if param.name == "stream":
            kwargs[param.name] = False
            continue
        if not param.required and param.default is None and not _param_has_file_format(param):
            continue
        kwargs[param.name] = _fake_value(param, files)
    return kwargs


def _endpoint_by_suffix(service_def: ServiceDefinition, suffix: str) -> Optional[EndpointDefinition]:
    normalized_suffix = suffix if suffix.startswith("/") else f"/{suffix}"
    for endpoint in service_def.endpoints:
        if endpoint.path.rstrip("/").endswith(normalized_suffix.rstrip("/")):
            return endpoint
    return None


def _require_stream_endpoint(service_def: ServiceDefinition, leaf: str) -> EndpointDefinition:
    """Resolve /text, /video or streaming /chat without colliding with schema routes."""
    suffix = leaf if leaf.startswith("/") else f"/{leaf}"
    candidates = [
        endpoint
        for endpoint in service_def.endpoints
        if endpoint.path.rstrip("/").endswith(suffix.rstrip("/"))
        and ("/streaming/" in f"{endpoint.path}/" or endpoint.path.count("/") == 1)
    ]
    if not candidates:
        pytest.skip(f"Streaming endpoint {suffix!r} is not exposed by {SERVICE_URL}")
    return candidates[0]


def _choice_message(result: dict) -> str:
    return result["choices"][0]["message"]["content"]


def _collect_stream_text(job) -> str:
    session = job.stream()
    try:
        if session.is_sse:
            return "".join(chunk_text(chunk) for chunk in session.iter_chunks())
        return b"".join(session.iter_bytes()).decode("utf-8", errors="replace")
    finally:
        session.close()


def _collect_stream_bytes(job) -> bytes:
    session = job.stream()
    try:
        data = b"".join(session.iter_bytes())
        if session.is_sse:
            parsed = assemble_stream_bytes(data, is_sse=True)
            if isinstance(parsed, bytes):
                return parsed
            if isinstance(parsed, str):
                return parsed.encode("utf-8")
        return data
    finally:
        session.close()


def _coalesce_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, VideoFile):
        return value.to_bytes()
    if isinstance(value, str):
        return value.encode("latin-1")
    raise AssertionError(f"Expected bytes-like stream result, got {type(value)!r}")


def _is_infrastructure_endpoint(endpoint: EndpointDefinition) -> bool:
    """Skip job control routes exposed in OpenAPI (status/cancel/stream)."""
    path = endpoint.path.rstrip("/")
    segments = [segment for segment in path.split("/") if segment and not segment.startswith("{")]
    if not segments:
        return False
    if segments[-1] in {"status", "cancel", "stream", "health"}:
        return True
    return False


def _is_dedicated_stream_endpoint(endpoint: EndpointDefinition) -> bool:
    """Endpoints covered by test_streaming_* rather than the generic iteration loop."""
    path = endpoint.path.rstrip("/")
    if path.endswith("/health"):
        return True
    if path.endswith("/text") or path.endswith("/video"):
        return True
    if not path.endswith("/chat"):
        return False
    if "/streaming/" in f"{path}/":
        return True
    return path.count("/") == 1


def _returns_media(endpoint: EndpointDefinition) -> bool:
    path = endpoint.path.rstrip("/")
    if path.endswith("-none"):
        return False
    return any(marker in path for marker in MEDIA_RETURN_PATH_MARKERS)


def _assert_known_result(endpoint: EndpointDefinition, result: Any) -> None:
    path = endpoint.path.rstrip("/")

    if path.endswith("/predict"):
        assert result == "testtest"
        return

    if path.endswith("/scalars"):
        assert result["text"] == "test"
        assert result["count"] == 2
        return

    if path.endswith("/chat-extended"):
        assert "[pirate]" in _choice_message(result)
        return

    if path.endswith("/chat-raw") or path.endswith("/chat-typed"):
        assert _choice_message(result) == "hello there"
        return

    if path.endswith("/completion-raw"):
        assert result["choices"][0]["text"] == "completed"
        return

    if path.endswith("/embedding-raw"):
        assert result["data"][0]["embedding"] == [0.1, 0.2, 0.3]


def test_iterate_all_endpoints():
    """Submit every non-streaming endpoint with schema-aware or generic fake inputs."""
    client = _client()
    service_def = _service_def()
    files = _test_files()

    for endpoint in service_def.endpoints:
        if _is_dedicated_stream_endpoint(endpoint) or _is_infrastructure_endpoint(endpoint):
            continue

        kwargs = _kwargs_for_endpoint(endpoint, files)
        job = client.submit_job(endpoint.path, **kwargs)
        result = job.wait_for_result(timeout_s=JOB_TIMEOUT_S)
        _assert_known_result(endpoint, result)


def test_streaming_text():
    """Plain token generator: iterate chunks and assemble via get_result()."""
    client = _client()
    endpoint = _require_stream_endpoint(_service_def(), "/text")
    expected = "".join(TEXT_TOKENS)

    stream_job = client.submit_job(endpoint.path)
    streamed = _collect_stream_text(stream_job)
    assert streamed == expected

    result_job = client.submit_job(endpoint.path)
    assert result_job.get_result(timeout_s=JOB_TIMEOUT_S) == expected


def test_streaming_video():
    """Binary frame generator: raw bytes stream and MediaToolkit assembly."""
    client = _client()
    endpoint = _require_stream_endpoint(_service_def(), "/video")
    expected_bytes = b"".join(VIDEO_FRAMES)

    stream_job = client.submit_job(endpoint.path)
    streamed = _collect_stream_bytes(stream_job)
    assert streamed == expected_bytes

    result_job = client.submit_job(endpoint.path)
    assembled = result_job.get_result(timeout_s=JOB_TIMEOUT_S)
    if isinstance(assembled, VideoFile):
        assert assembled.file_size() == len(expected_bytes)
    else:
        assert _coalesce_bytes(assembled) == expected_bytes


def test_streaming_chat_schema():
    """Schema-backed SSE chat: stream deltas and get_result() without streaming first."""
    client = _client()
    endpoint = _require_stream_endpoint(_service_def(), "/chat")
    if not endpoint.supports_streaming:
        pytest.skip(f"{endpoint.path} does not advertise stream support")

    payload = {"messages": [{"role": "user", "content": "hi"}], "stream": True}
    expected = "".join(CHAT_TOKENS)

    stream_job = client.submit_job(endpoint.path, **payload)
    assert _collect_stream_text(stream_job) == expected

    result_job = client.submit_job(endpoint.path, **payload)
    result = result_job.get_result(timeout_s=JOB_TIMEOUT_S)
    if isinstance(result, dict):
        assert _choice_message(result) == expected
    else:
        assert result == expected

    sync_job = client.submit_job(
        endpoint.path,
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
    )
    sync_result = sync_job.wait_for_result(timeout_s=JOB_TIMEOUT_S)
    if isinstance(sync_result, dict):
        assert _choice_message(sync_result) == expected
    else:
        assert sync_result == expected


def test_media_results_are_media_toolkit_files():
    """Media-bearing endpoints return media-toolkit file objects (or nested media payloads)."""
    client = _client()
    service_def = _service_def()
    files = _test_files()
    checked = 0

    for endpoint in service_def.endpoints:
        if not _returns_media(endpoint):
            continue

        kwargs = _kwargs_for_endpoint(endpoint, files)
        result = client.submit_job(endpoint.path, **kwargs).wait_for_result(timeout_s=JOB_TIMEOUT_S)

        if isinstance(result, MediaFile):
            assert result.file_size() > 0
            checked += 1
            continue

        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list) and data and isinstance(data[0], MediaFile):
                assert data[0].file_size() > 0
                checked += 1
                continue

        pytest.fail(f"{endpoint.path} did not return a media-toolkit file")

    if checked == 0:
        pytest.skip("No media-returning endpoints are exposed by the current service launch")


def test_connect_chat_extended():
    client = _client()
    endpoint = _endpoint_by_suffix(_service_def(), "/chat-extended")
    if endpoint is None:
        pytest.skip(f"Endpoint /chat-extended is not exposed by {SERVICE_URL}")
    result = client.submit_job(
        endpoint.path,
        messages=[{"role": "user", "content": "ahoy"}],
        persona="captain",
    ).wait_for_result(timeout_s=JOB_TIMEOUT_S)
    assert _choice_message(result) == "[captain] ahoy"


def _main_tests() -> Iterable[str]:
    return (
        "test_iterate_all_endpoints",
        "test_streaming_text",
        "test_streaming_video",
        "test_streaming_chat_schema",
        "test_media_results_are_media_toolkit_files",
        "test_connect_chat_extended",
    )


if __name__ == "__main__":
    for test_name in _main_tests():
        print(f"\n=== {test_name} ===")
        globals()[test_name]()
