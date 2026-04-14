# fastSDK Technical README

## TL;DR
`fastsdk` turns an API description into a Python client workflow that is easy to call from normal Python code.

It has three major responsibilities:
- parse API specifications into internal service models
- generate Python SDK/client code from those models
- execute requests, file handling, polling, and job lifecycle management for long-running APIs

For job-based APIs such as APIPod, Runpod, Socaity, or Replicate, `fastsdk` delegates runtime orchestration to `meseex`.

## Mental Model
Think of `fastsdk` as two connected subsystems:

1. Definition layer
   - Loads `openapi.json` or provider-specific specs
   - Normalizes them into a `ServiceDefinition`
   - Stores them in `Registry`

2. Runtime layer
   - Formats requests
   - Loads and uploads files
   - sends HTTP requests
   - polls job status when the provider is asynchronous
   - parses final results back into Python-friendly objects

The generated SDKs and temporary clients are just convenient entry points into those two layers.

## Easy Overview
The rough data flow is:

1. `FastSDK` loads or receives a service specification.
2. The spec is parsed into a `ServiceDefinition` and `EndpointDefinition`s.
3. A client is generated or constructed dynamically.
4. Calling an endpoint creates an `APISeex` job.
5. `ApiJobManager` executes that job through `MeseexBox`.
6. The job runs a small pipeline:
   - prepare request
   - load local files
   - upload files when needed
   - send request
   - poll remote job status when applicable
   - post-process result

## Core Building Blocks
### `FastSDK`
Main façade for users.

Important responsibilities:
- load a service definition from spec input
- register services in `Registry`
- create generated SDK files
- create temporary or permanent clients
- expose the shared `ApiJobManager`

### `ServiceDefinition` and `Registry`
These define the internal contract for a service:
- endpoints
- parameters
- provider metadata
- service address
- specification type

`Registry` is the in-memory registry used by runtime code.

### Specification Loading
The service specification loader does provider-aware parsing:
- generic OpenAPI
- Runpod
- Socaity / APIPod variants
- Replicate-style prediction APIs

The goal is to normalize different providers into one internal definition model.

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
- `APIClientReplicate`

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

## Why The Architecture Looks Like This
The package is optimized for a common real-world scenario:
- Python users mostly write synchronous application code
- service interaction is dominated by network I/O
- many requests may be active at once
- some requests also require file preprocessing and uploads

Using `meseex` lets `fastsdk` expose a simple sync-friendly API while still executing request-heavy work efficiently.

