<p align="center">
  <img src="docs/assets/logo.png" alt="fastSDK logo" height="200" />
</p>

<p align="center">
  <a href="https://pypi.org/project/fastsdk/"><img src="https://img.shields.io/pypi/v/fastsdk?labelColor=000000&color=76B900" alt="PyPI version"></a>
  <a href="https://pypi.org/project/fastsdk/"><img src="https://img.shields.io/pypi/pyversions/fastsdk?labelColor=000000&color=76B900" alt="Python versions"></a>
  <a href="https://github.com/SocAIty/fastSDK"><img src="https://img.shields.io/badge/github-SocAIty%2FfastSDK-76B900?labelColor=000000" alt="GitHub"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-76B900?labelColor=000000" alt="License"></a>
</p>
<h3 align="center" style="margin-top:-10px">Call any AI / web service like a native Python function</h3>

fastSDK turns any hosted service — OpenAPI/FastAPI, [APIPod](https://github.com/SocAIty/APIPod), [RunPod](https://www.runpod.io), [Replicate](https://replicate.com), [Cog](https://github.com/replicate/cog) — into a Python client that feels like a local library: typed methods, file upload/download, async job handling and parallel execution included.

Point it at a service. Call it like a function. That's the whole idea.

```python
import fastsdk

client = fastsdk.connect("http://localhost:8009")
job = client.submit_job("/text2voice", text="hello world")
audio = job.get_result()
audio.save("hello.mp3")
```

## Why fastSDK?

Calling a web service from Python sounds trivial until you actually do it in production:
you wait synchronously on long-running ML jobs, you hand-write request code for every endpoint, you fight with file uploads (try sending a 1 GB video through `requests`), you poll job status loops, and you reinvent threading to run requests in parallel.

fastSDK solves exactly that, and nothing else:

- **One call = one job.** Every call returns a job object immediately. Get the result when you need it, run hundreds of jobs in parallel meanwhile.
- **Files just work.** Images, audio, video are handled by [media-toolkit](https://github.com/SocAIty/media-toolkit) — local paths, URLs, bytes or numpy arrays in; media objects out. Large files are uploaded via cloud storage (S3, Azure) when configured.
- **Job-based providers are normalized.** Replicate, RunPod serverless, APIPod and Socaity all expose "submit, then poll" APIs with different wire formats. fastSDK handles submission, polling, progress and cancellation uniformly.
- **Codegen when you want it, not when you don't.** Use `connect()` for instant access, or `generate_stub()` to get a typed `.py` client with one method per endpoint - autocomplete and docstrings included.

## Installation

```bash
pip install fastsdk           # core
pip install fastsdk[replicate]  # + Replicate model support
```

## Get started

### Option A: connect — use a service right now

No files, no codegen. Works with a URL, an `openapi.json` path, or a Replicate model reference.

```python
import fastsdk

client = fastsdk.connect("http://localhost:8009")
job = client.submit_job("/text2voice", text="hello world")
result = job.get_result()
```

### Option B: generate_stub — typed clients for real projects

Generates a `.py` file with one typed method per endpoint. This is your SDK.

```python
import fastsdk

stub = fastsdk.generate_stub("http://localhost:8009", save_path="clients/")
print(stub.path, stub.class_name)

# use it immediately ...
client = stub.client()
job = client.text2voice(text="hello world")

# ... or import it in your next run like any other module
# from clients.speechcraft import speechcraft
# client = speechcraft()
```

Re-running `generate_stub` is safe: the file is overwritten and the service registration is updated, not duplicated.

### Replicate models

Official models (called via `/v1/models/{owner}/{name}/predictions`) and community models (called via `/v1/predictions` with a version) are resolved automatically — you just name the model:

```python
import fastsdk  # requires: pip install fastsdk[replicate] and REPLICATE_API_KEY

stub = fastsdk.generate_stub("replicate:black-forest-labs/flux-schnell", save_path="clients/")
flux = stub.client()
job = flux(prompt="a t-rex on a skateboard")
image = job.get_result()
```

### Working with jobs

```python
job = client.swap_img_to_img(source_img="face1.jpg", target_img="face2.jpg")
job.get_result()          # block until done and return the result
job.cancel()              # cancel locally and remotely (provider permitting)

# run many jobs in parallel - this is where fastSDK shines
jobs = [client.text2voice(text=t) for t in hundred_texts]
results = fastsdk.gather_results(jobs)
```

### API keys

Pass `api_key=...` to `connect()`, `generate_stub()` or the client constructor — or set environment variables: `REPLICATE_API_KEY`, `RUNPOD_API_KEY`, `SOCAITY_API_KEY`, or `<SERVICE_ID>_API_KEY` for your own services.

## The four concepts

| Concept | What it is |
|---|---|
| **Service** | An `AIService` (from socaity-schemas) with one deployment: hosting provider, address, and the parsed `ServiceContract` (endpoints, parameters, whether responses are polled jobs). Get one with `fastsdk.inspect_service(source)`, it has no side effects. |
| **Registry** | An in-process directory of services, shared by all clients. `register_service()` adds to it; generated stubs look their service up in it by ID. |
| **Client** | The runtime object you call (`FastClient`). It submits jobs to the service. `connect()` gives you a generic one instantly. |
| **Stub** | A generated `.py` file containing a client subclass with one typed method per endpoint. Made by `generate_stub()`; it's plain code — read it, version it, ship it. |

## CLI

Everything above also works from the terminal — same verbs, same behavior:

```bash
# What can this service do?
fastsdk inspect http://localhost:8009

# Generate a typed client stub
fastsdk generate http://localhost:8009 -o clients/ --name SpeechCraft
fastsdk generate replicate:black-forest-labs/flux-schnell --api-key r8_...

# Call an endpoint without writing any code (curl for AI services)
fastsdk call http://localhost:8009 /text2voice --text "hello world" -o hello.mp3

# Keep services around by name (persisted in ~/.fastsdk/registry)
fastsdk registry add http://localhost:8009 --name speechcraft
fastsdk registry list
fastsdk call speechcraft /text2voice --text "hi again"
```

## Service compatibility

Works out of the box with:
- [APIPod](https://github.com/SocAIty/APIPod) services (job-based, the natural counterpart to fastSDK)
- [Replicate](https://replicate.com) models (official and community)
- [RunPod serverless](https://www.runpod.io/serverless-gpu) endpoints
- [Cog](https://github.com/replicate/cog) services
- Any OpenAPI 3.0 service ([FastAPI](https://github.com/tiangolo/fastapi), [Flask](https://flask.palletsprojects.com/), ...)
- [Socaity.ai](https://www.socaity.ai) services

## fastSDK + APIPod

<img src="https://github.com/SocAIty/APIPod/blob/main/docs/fastsdk_to_apipod.png?raw=true" width="50%" />

[APIPod](https://github.com/SocAIty/APIPod) builds and deploys the services; fastSDK consumes them. Two beating hearts :two_hearts: for service ↔ client interaction.


## Contribute

We at SocAIty want to provide the best tools to bring generative AI to the cloud.
Report bugs, ideas and feature requests in the issues section.
fastSDK is MIT-licensed and free to use. Leave a star to support us!

---
<p align="center">
  Made with ❤️ by <a href="https://www.socaity.ai?utm_source=github&utm_content=fastsdk-20-29-06-2026">SocAIty</a>
</p>
