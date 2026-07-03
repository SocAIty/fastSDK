# fastSDK Technical README

## TL;DR
`fastsdk` turns an API description into a Python client workflow that is easy to call from normal Python code.

It has three major responsibilities:
- parse API specifications into internal service models (the *definition layer*)
- generate Python client stub code from those models (the *stub factory*)
- execute requests, file handling, polling, and job lifecycle management for long-running APIs (the *runtime layer*)

For job-based APIs such as APIPod, RunPod, Socaity, or Replicate, `fastsdk` delegates runtime orchestration to `meseex`.

## Public API Surface

The package exposes module-level functions (`fastsdk/api.py`). They wrap a process-wide
`FastSDK` singleton, which is intentionally kept out of the public surface:

| Function | Side effects | Returns |
|---|---|---|
| `fastsdk.inspect_service(source)` | none (pure) | `ServiceDefinition` |
| `fastsdk.register_service(source)` | upserts into the registry | `ServiceDefinition` |
| `fastsdk.connect(source)` | registers temporarily | `FastClient` (service deregistered when the client is deleted) |
| `fastsdk.generate_stub(source)` | writes a `.py` file + registers the service | `GeneratedStub` |
| `fastsdk.get_service / list_services / remove_service` | registry reads/writes | - |

`source` is always the same union: URL, `openapi.json` file path, spec dict, `ServiceDefinition`,
Replicate model reference (`"replicate:owner/name"`, `"https://replicate.com/owner/name"`, bare `"owner/name"`),
or — where it makes sense — an already registered service ID/name.

Deprecated aliases (warn via `DeprecationWarning`, will be removed eventually):
`generate_stub`, `create_temporary_client` → `connect`,
`load_service_definition` → `inspect_service`, `DynamicClient`/`TemporaryClient` → `FastClient(..., temporary=...)`.

## Mental Model
Think of `fastsdk` as two connected subsystems:

1. Definition layer
   - Loads `openapi.json` or provider-specific specs
   - Normalizes them into a `ServiceDefinition`
   - Stores them in the `Registry`

2. Runtime layer
   - Formats requests
   - Loads and uploads files
   - Sends HTTP requests
   - Polls job status when the provider is asynchronous
   - Parses final results back into Python-friendly objects

Generated stubs and `connect()` clients are just convenient entry points into those two layers.

## Easy Overview
The rough data flow is:

1. A service specification is loaded (`inspect_service`) and parsed into a `ServiceDefinition` with `EndpointDefinition`s.
2. The definition is registered in the `Registry` (`register_service`, or implicitly by `connect`/`generate_stub`).
3. A client is constructed (`FastClient`) or generated (`GeneratedStub` → `.py` file with a `FastClient` subclass).
4. Calling an endpoint creates an `APISeex` job.
5. `ApiJobManager` executes that job through `MeseexBox`.
6. The job runs a small pipeline:
   - prepare request
   - load local files
   - upload files when needed
   - send request
   - poll remote job status when applicable
   - post-process result

## Package Layout

```
fastsdk/
  api.py                          # module-level public API (connect, generate_stub, ...)
  cli.py                          # `fastsdk` console entry point
  fastSDK.py                      # FastSDK singleton facade (registry + job manager wiring)
  fastClient.py                   # FastClient runtime client (base class of generated stubs)
  fastStub.py                     # Contains the Stub that is generated
  sdk_factory/
    sdk_factory.py                # generate_stub(), Jinja2-based codegen
    sdk_template.j2               # default stub template
  service_specification_loader/
    spec_loader.py                # load openapi.json from URL/file/dict (with fallbacks)
    runpod_open_api_loader.py     # fetch openapi.json through a RunPod serverless job
    replicate_loader.py           # Replicate model -> ServiceDefinition (optional `replicate` dep)
  service_interaction/
    api_job_manager.py            # composition root + submit + meseex wiring
    job_tasks.py                  # meseex task implementations (prepare, poll, send, ...)
    job_runtime.py                # per-job lifecycle controller (cancel/stream/assemble + guards)
    async_bridge.py               # single async->sync bridge over the meseex loop
    provider_factory.py           # provider type resolution + ProviderStack assembly
    provider_stack_registry.py    # load/cache provider stacks per service id
    pipeline_planner.py           # ordered meseex task list for one endpoint
    api_seex.py                   # APISeex job handle (a specialized MrMeseex)
    request/                      # APIClient + provider subclasses, FileHandler
    response/                     # ResponseParser, BaseJobResponse, StreamSession, status mapping
```

## Core Building Blocks

### `FastSDK` (internal singleton)
One instance per process. It owns:
- the `Registry` (lazy-created, in-memory by default)
- the `ProviderStackRegistry` (lazy-created)
- the `ApiJobManager` (lazy-created, receives the stack registry)

and implements `inspect_service`, `register_service` (upsert), `generate_stub`, `connect`.
All clients and stubs in a process therefore share one registry and one job manager.
Advanced users can swap the registry (e.g. for a persistent or DB-backed one) via
`FastSDK().service_registry = Registry(service_store=...)`.

### `ServiceDefinition` and `Registry`
These define the internal contract for a service (from `socaity_schemas.service_definitions`, used by `apipod_registry`):
- endpoints and parameters
- provider metadata
- service address
- specification type (`openapi`, `apipod`, `runpod`, `replicate`, `socaity`, ...)

`Registry` maps service IDs and normalized display names to definitions.

**Registration is an upsert**: `FastSDK.register_service()` replaces an existing entry with the same ID
instead of raising. This makes scripts idempotent — re-running `generate_stub`/`register_service`
never fails with "already registered".

**Lifetime**: the default registry is in-memory. A stub imported in a fresh process must find its
service in the registry; either `register_service(...)` first, regenerate the stub, or attach a
persistent store. The CLI attaches a `FileSystemStore` under `~/.fastsdk/registry` for its
`registry` subcommand, so CLI-registered services survive across invocations.

### `FastClient`
The single runtime client class (the previous `DynamicClient`/`TemporaryClient` subclasses are
collapsed into attributes):

```python
FastClient(service, api_key=None, temporary=False, service_name_or_id=None, **load_kwargs)
```

- `service`: any source. Strings are first looked up in the registry; on miss they are loaded
  and registered as a spec source.
- `service_name_or_id`: strict registry lookup (no loading). This is the path generated stubs use:
  `super().__init__(service_name_or_id="<service-id>")`. It raises with a helpful message if the
  service was never registered in this process.
- `temporary=True`: the service is removed from the registry when the client is deleted/closed.
  `FastClient` is also a context manager (`with fastsdk.connect(...) as client:`).
- API keys are resolved from the argument, then from environment variables
  (`SOCAITY_API_KEY`, `RUNPOD_API_KEY`, `REPLICATE_API_KEY`, or `<SERVICE_ID>_API_KEY`).

`submit_job(endpoint_id, **params)` is the generic invocation path; generated stub methods are
thin typed wrappers around it.

### Stub Generation (`sdk_factory`)
`generate_stub(service_definition, save_path, class_name, template)` renders the Jinja2 template
into a `.py` file containing a `FastClient` subclass:
- one method per endpoint, with type hints derived from the parameter definitions
  (media formats map to `media_toolkit` types: `ImageFile`, `AudioFile`, `VideoFile`, `MediaFile`)
- parameter defaults and docstrings from the spec
- `run` and `__call__` aliases for the primary endpoint

It returns a `GeneratedStub` dataclass:
- `.path`, `.class_name`, `.service_definition`
- `.client(api_key=None)` — imports the generated file and instantiates the class (works
  immediately because the service was just registered)
- iterable for backwards compatibility (`path, name, sd = generate_stub(...)`)

### Specification Loading
The definition layer does provider-aware parsing:
- functions to load from urls with `/openapi.json`-style 
- from files
- RunPod serverless (the spec itself is fetched through a RunPod job, see `runpod_open_api_loader`)
- Replicate (see below)
- Socaity / APIPod variants

The goal is to normalize different providers into one internal definition model.

### Replicate Loading (`replicate_loader`)
Replicate has two invocation URL schemes, and the loader resolves them automatically:

- **Official models** (`is_official` on the model object / REST response):
  `POST https://api.replicate.com/v1/models/{owner}/{name}/predictions` — no version needed.
- **Community models**:
  `POST https://api.replicate.com/v1/predictions` — the model version id is sent in the request body
  (`APIClientReplicate` injects it from `ReplicateServiceAddress.version`).

Flow: `parse_replicate_model_ref()` detects model references (`replicate:owner/name`, replicate.com
URLs, bare `owner/name` strings that aren't local files). `load_replicate_service()` then uses the
`replicate` package (an **optional dependency**, enforced lazily with media-toolkit's
`@requires("replicate")` decorator) to fetch `model.latest_version.openapi_schema`, parses it, and
builds the service address for the right scheme. Service IDs are stable
(`replicate-{owner}-{name}`), so reloading the same model upserts instead of duplicating.

### Lifecycle architecture: three boundaries
Transport ownership is split across three files so each concern has one home.

**`ApiJobManager`** (`api_job_manager.py`) is the process-level orchestrator and composition root.
It wires a ``MeseexBox`` with handlers from ``JobTasks``, owns one shared ``AsyncBridge``,
and exposes ``submit_job(...)``. It does not load provider stacks, plan pipelines beyond
delegating to ``PipelinePlanner``, or implement task bodies.

``FastClient`` loads stacks via ``FastSDK.provider_stacks.load(...)`` before submission.
``submit_job(...)`` calls ``PipelinePlanner.plan(...)``, builds an ``APISeex``, attaches a
per-job ``JobRuntime``, and summons it into the ``MeseexBox``.

**`ProviderStackRegistry`** (`provider_stack_registry.py`) caches ``ProviderStack`` instances
per service id. ``load(service_name_or_id, api_key)`` resolves the service from the registry
and calls ``ProviderFactory.build(...)``. Task handlers and ``JobRuntime`` read stacks through
this registry.

**`JobTasks`** (`job_tasks.py`) implements the meseex pipeline steps: prepare request, load/upload
files, send request, poll status, process result. Polling logic and the ``@polling_task`` decorator
live here, not on the manager.

**`ProviderFactory`** (`provider_factory.py`) resolves provider type from a ``ServiceDefinition``
and returns a frozen ``ProviderStack``: ``APIClient``, ``FileHandler``, and cached ``ResponseParser``.

**`PipelinePlanner`** (`pipeline_planner.py`) is a pure planner: given a service, endpoint, and
optional stack, it returns the ordered task names with steps omitted when not needed.

**`JobRuntime`** (`job_runtime.py`) is the per-job lifecycle controller, created once per job. It
owns one job's transport state:
- the single active `StreamSession` slot (`None` or exactly one session)
- a readiness `Event` fed by the polling/send tasks as job state advances
- cancellation policy (remote cancel plus terminal-state reconciliation)
- stream teardown when a cancel resolves

It enforces the invariants with guards: at most one active stream per job, no stream open after a
terminal state with no live source, and active streams close on cancel.

**`APISeex`** (`api_seex.py`) is the user ticket: identity plus a progress/result view (`response`,
`runtime_info`, `result`). Its lifecycle methods (`cancel()`, `stream()`, streaming-aware
`get_result()`) are one-line delegates to its `JobRuntime`. The handle never touches an `APIClient`,
a `ResponseParser`, the `AsyncBridge`, or the `MeseexBox` directly.

Boundary rule: `api_seex.py` imports only `meseex` and schemas (the `JobRuntime` type is a
type-check-only import). No client, parser, or bridge imports belong there.

### `AsyncBridge`
The single async->sync bridge (`async_bridge.py`). The `MeseexBox` runs one asyncio loop in a
background thread, and every httpx response fastsdk creates is bound to that loop, so any follow-up
coroutine (poll, cancel, open stream, close) must run there. `AsyncBridge.run(coro_func, *args,
timeout_s=...)` schedules the coroutine on the loop and blocks on a `concurrent.futures.Future`
with a timeout. It is the only place that crosses the boundary, which keeps runtime logic free of
sleep/busy-wait loops.

## Runtime Pipeline In Detail
### 1. Prepare request
`APIClient.format_request_params(...)` maps endpoint parameters into:
- query params
- body params
- file params
- headers
- target URL

### 2. Load local media
If endpoint parameters include files, `FileHandler.load_files_from_disk(...)` converts them into `MediaDict` objects.

### 3. Upload large files
If the provider is configured with cloud upload support, `FileHandler.upload_files(...)` uploads oversized assets and replaces them with remote URLs.

### 4. Send request
`APIClient.send_request(...)` sends the HTTP request.

Provider subclasses adapt protocol details:
- `APIClientRunpod`
- `APIClientSocaity`
- `APIClientReplicate` (moves query/file params into the JSON body as `{"input": ...}`, adds `version` for community models)

### 5. Poll status
If the response is job-based, `_poll_status(...)` keeps polling through `@polling_task(...)` until the remote job is terminal.

### 6. Process result
`ResponseParser` and result-specific parsers convert provider responses into:
- `BaseJobResponse`
- media objects
- plain Python results

## How `meseex` Fits In
`fastsdk` does not implement its own thread/event-loop orchestration.

Instead:
- `APISeex` is a specialized `MrMeseex`
- `ApiJobManager` defines the request workflow tasks
- `MeseexBox` schedules and runs those tasks

This keeps HTTP-heavy workflows efficient in regular synchronous applications while still using async I/O internally.

## Response Model
The central normalized response type is `BaseJobResponse`.

It captures:
- remote job id
- unified status via `APIJobStatus`
- progress
- error
- result
- `refresh_job_url`
- `cancel_job_url`

Provider-specific parsers fill this model from different wire formats.

## Streaming

Streaming reuses the existing job pipeline and adds one consumer abstraction. Three modes, one API:

1. Direct SSE: `stream=True` on a chat-like schema returns `text/event-stream` immediately. No job, no polling.
2. Raw binary: e.g. `SpeechRequest(stream=True)` returns audio/video bytes directly.
3. Job + stream link: a normal JSON job handle that also exposes a live `links.stream` (Socaity) or `urls.stream` (Replicate) while running.

### Public surface
One entrypoint: ``job.stream()``. It returns a ``StreamSession`` you iterate sync (``iter_*``) or
async (``aiter_*``); the session auto-selects SSE chunks or raw bytes from the response content
type. There is no separate ``astream()``: a single session already serves both consumer styles, so
a second method would only duplicate semantics and invite drift.

``job.get_result()`` for streaming jobs delegates to the runtime to assemble the full payload (media
file or joined SSE text) when the caller never invoked ``stream()``.

### How it routes
`APISeex.stream()` delegates to its `JobRuntime`. The runtime resolves the stream source in this
order:
1. ``job.direct_response``: an open SSE/raw response captured at send time (no polling job).
2. provider ``links.stream`` / ``urls.stream``: opened via ``APIClient.open_stream`` once the poll
   loop exposes the URL.

The runtime blocks on a readiness `Event` (set by the send/poll tasks as state advances) instead of
busy-waiting, takes the single session slot, and rejects a second concurrent `stream()`. The
response is created and read on `meseex`'s background event loop via the `AsyncBridge`.
`StreamSession` hands items across threads through a queue, so callers consume from any thread or
loop without touching that loop directly.

Provider transport models live in ``socaity_schemas.transport`` (imported directly, no local duplicate module).
Byte-chunk streams are assembled via ``media_toolkit.media_from_any``.

## How Cancellation Works
Cancellation has two layers: local workflow cancellation and remote provider cancellation.

### Public entry point
Users call:

```python
job = client.submit_job(...)
cancel_info = job.cancel()
```

### Technical flow
There is one cancel implementation: `JobRuntime.cancel(wait=...)`. The handle's `APISeex.cancel(...)`
just delegates to its runtime.

1. `job` is an `APISeex`; `job.cancel(...)` calls `JobRuntime.cancel(...)`.
2. The runtime closes any active stream slot first.
3. It checks the latest known response.
4. If no remote job exists yet:
   - the local workflow is cancelled through `MeseexBox.cancel_meseex(...)`
5. If a remote job exists and exposes a cancel URL:
   - `APIClient.cancel_job(...)` sends the provider-specific cancel request (via the `AsyncBridge`)
   - with `wait=True`, the runtime polls until the provider reports `CANCELLED`, or until another terminal state is reached
6. Once cancellation is confirmed, `MeseexBox` finalizes the local `MrMeseex` as cancelled

### Important nuance
Remote cancellation is not assumed just because the cancel endpoint was called.

The implementation waits for the provider to confirm cancellation. If the provider instead reports `FINISHED`, `FAILED`, or another non-cancellable terminal state, that remote state is returned and the workflow is not forcefully rewritten into `CANCELLED`.

### Practical consequence
- queued local jobs cancel immediately
- in-flight async pipeline steps usually cancel quickly
- a provider may still reject cancellation because the remote job has already progressed too far

## The CLI
`fastsdk/cli.py` (console script `fastsdk`, argparse-based) mirrors the Python API one-to-one:

| Command | Python equivalent |
|---|---|
| `fastsdk inspect <source>` | `inspect_service(source)` + pretty printing of endpoints/params |
| `fastsdk generate <source> -o <path> --name <Class>` | `generate_stub(...)` + prints the import line |
| `fastsdk call <source> <endpoint> --param value ...` | `FastClient(source).submit_job(endpoint, ...)` |
| `fastsdk registry list/add/remove/show` | persistent registry management |

Implementation notes:
- Unknown `--key value` pairs of `call` are parsed into endpoint parameters; values go through
  `json.loads` first (so `--steps 4` is an int, `--flag` alone is `true`), falling back to strings.
- Media results (anything with `.save()`) are written to `-o`/their original filename; dict/list
  results are printed as JSON.
- The `registry` subcommand wraps a `Registry` backed by `FileSystemStore`
  (`~/.fastsdk/registry`, overridable with the `FASTSDK_REGISTRY_PATH` env var). All other commands
  also resolve their `<source>` against this store first, so `fastsdk call speechcraft ...` works
  after a `fastsdk registry add ... --name speechcraft`.

## Why The Architecture Looks Like This
The package is optimized for a common real-world scenario:
- Python users mostly write synchronous application code
- service interaction is dominated by network I/O
- many requests may be active at once
- some requests also require file preprocessing and uploads

Using `meseex` lets `fastsdk` expose a simple sync-friendly API while still executing request-heavy work efficiently.
