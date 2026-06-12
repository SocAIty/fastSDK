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
`create_sdk` → `generate_stub`, `create_temporary_client` → `connect`,
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
    api_job_manager.py            # runtime orchestrator
    api_seex.py                   # APISeex job (a specialized MrMeseex)
    request/                      # APIClient + provider subclasses, FileHandler
    response/                     # ResponseParser, BaseJobResponse, status mapping
```

## Core Building Blocks

### `FastSDK` (internal singleton)
One instance per process. It owns:
- the `Registry` (lazy-created, in-memory by default)
- the `ApiJobManager` (lazy-created)

and implements `inspect_service`, `register_service` (upsert), `generate_stub`, `connect`.
All clients and stubs in a process therefore share one registry and one job manager.
Advanced users can swap the registry (e.g. for a persistent or DB-backed one) via
`FastSDK().service_registry = Registry(service_store=...)`.

### `ServiceDefinition` and `Registry`
These define the internal contract for a service (from `apipod_registry`):
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
- generic OpenAPI (`spec_loader.load_spec`: direct URL, `/openapi.json`-style fallbacks, file, dict)
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

### `ApiJobManager`
This is the runtime orchestrator.

It owns:
- provider-specific `APIClient` instances
- provider-aware `FileHandler`s
- the `ResponseParser`
- a `MeseexBox` that executes request jobs

The `submit_job(...)` method builds an `APISeex` with the exact task list needed for a request.

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

## How Cancellation Works
Cancellation has two layers: local workflow cancellation and remote provider cancellation.

### Public entry point
Users call:

```python
job = client.submit_job(...)
cancel_info = job.cancel()
```

### Technical flow
1. `job` is an `APISeex`.
2. `APISeex.cancel()` checks the latest known response.
3. If no remote job exists yet:
   - the local workflow is cancelled through `MeseexBox.cancel_meseex(...)`
4. If a remote job exists and exposes `cancel_job_url`:
   - `APIClient.cancel_job(...)` sends the provider-specific cancel request
   - `APISeex` polls until the provider reports `CANCELLED`, or until another terminal state is reached
5. Once cancellation is confirmed, `MeseexBox` finalizes the local `MrMeseex` as cancelled

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
