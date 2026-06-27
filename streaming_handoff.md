# Your Task

Add streaming to fastSDK so higher-level libraries (like langchain) to get one stable API. fastSDK owns transport (polling, direct, streaming), parsing, and MediaToolkit bridging.
I already implemented parts of the streaming functionality both in fastSDK, MediaToolkit and moved schemas to socaity-schemas.

## Three modes (one abstraction)

1. **Direct SSE** — `stream=True` on chat-like schemas; immediate `text/event-stream` with OpenAI-style chunks. No job polling.
2. **Raw binary** — e.g. `SpeechRequest(stream=True)`; response is audio/video bytes, not JSON. Parser currently buffers via `aread()`.
3. **Job + stream link** — initial JSON job handle; poll via `links.status`; optional `links.stream` (Socaity/Replicate) for live output while in progress.

Auto-select: use stream when request has `stream=True` (default) and endpoint supports it, or when poll response exposes a stream URL. Caller can still `wait_for_result()` to drain and get a final assembled result.

## Target public API

Keep `submit_job()` as entry point. Extend `APISeex`:
`stream=False` keeps current poll → parse → result behavior unchanged.
Open `links.stream` immediately after status returns the url in its response. 

## Implementation map

| Area | Action |
|---|---|
| `ApiJobManager.submit_job` | Skip `"Polling"` for direct SSE/raw; open `links.stream` during poll when present |
| `APIClient*` | Add `get_stream_url()`, `open_stream()` (Socaity, Replicate, Runpod-apipod) |
| `APISeex` | `stream()`, wire `StreamSession` from `direct_response` or stream URL |
| MediaToolkit | New HTTP-chunk adapter (see below) |

Suggested order: schemas dep → parser metadata → `StreamSession` + `APISeex.stream()` → client stream URLs → task routing → MediaToolkit bridge → stub aliases → tests (chat SSE, speech bytes, job+stream link).

## socaity-schemas

New shared package for APIPod Pydantic models (requests, responses, `ChatCompletionChunk`, FileModel variants). f
fastSDK imports from there instead of duplicating.
However, fastSDK only needs the JOB_RESPONSE_TYPES schemas because fastSDK stays a pure transport library.
fastSDK service_interaction is schema-agnostic.
Parser additions on `EndpointDefinition` `supports_streaming` — request schema has `stream: bool`

## MediaToolkit gap

Existing `AudioStream` / `VideoStream` and `AudioFile.from_stream()` expect a **complete** seekable container (`BytesIO`), not live httpx chunks.
Reuse: `AudioFile.from_audio_generator()`, `VideoFile.from_generators()`, `download_helper` httpx.stream pattern.
Add in media-toolkit (coordinate separately): HTTP byte iterator → incremental decode or buffer-then-PyAV; expose e.g. `HTTPMediaStream.iter_bytes()` / `to_media_file()`. fastSDK should depend on that interface, not expose raw httpx to callers.
Implement stream() and astream() give on submit_job the optional option for stream_media_as="bytes" or "auto"


## Key files

`api_job_manager.py`, `api_seex.py`, `response_parser.py`, `response_schemas.py`, `api_client*.py`, `sdk_factory/sdk_factory.py`, `APIPodRegistry/.../base_parser.py`, `service_definitions.py`, media-toolkit streaming adapter (new).

Finally briefly update the technical_readme(s) and 