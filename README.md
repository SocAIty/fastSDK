<p align="center">
  <img src="docs/assets/logo.png" alt="fastSDK logo" height="220" />
</p>

## fastSDK

Turn any hosted service into a typed Python client. Point fastSDK at an OpenAPI
spec and get a Python SDK with a method per endpoint — typed parameters, file
uploads, and built-in job handling for long-running calls.

<p align="center">
  <a href="https://pypi.org/project/fastsdk/"><img src="https://img.shields.io/pypi/v/fastsdk?labelColor=000000&color=76B900" alt="PyPI version"></a>
  <a href="https://pypi.org/project/fastsdk/"><img src="https://img.shields.io/pypi/pyversions/fastsdk?labelColor=000000&color=76B900" alt="Python versions"></a>
  <a href="https://github.com/SocAIty/fastSDK"><img src="https://img.shields.io/badge/github-SocAIty%2FfastSDK-76B900?labelColor=000000" alt="GitHub"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-76B900?labelColor=000000" alt="License"></a>
</p>

<h3 align="center">Turn any hosted service into a typed Python client.</h3>

<p align="center">
  Point fastSDK at an OpenAPI spec and get a Python client with a method per endpoint,<br>
  typed parameters, file uploads, and job handling. Call web APIs like plain functions.
</p>

## Why

You built a web service with [FastAPI](https://github.com/tiangolo/fastapi), Flask, [Cog](https://github.com/replicate/cog), or [APIPod](https://github.com/SocAIty/APIPod). Now you need a Python client.

Hand-writing one with `requests` works until it does not. You add endpoints. You run calls in parallel. You transfer a 1GB video and the request times out. You fall into threading and asyncio complexity, and the client drifts out of sync with the API.

fastSDK generates the client from your spec. Endpoints become typed methods. Files upload and stream. Long-running calls return a job you can wait on or cancel. The heavy I/O runs concurrently under the hood through [meseex](https://github.com/SocAIty/meseex), so your code stays synchronous and simple.

## Install

```bash
pip install fastsdk
```

## Quick start

Grab your service's `openapi.json` (usually at `http://localhost:8000/openapi.json`), then generate a client:

```python
from fastsdk import FastSDK

# generate a client file from the spec
FastSDK().create_sdk("openapi.json", save_path="my_service.py", class_name="MyService")
```

The generated file has one method per endpoint, with every parameter and default. Import it and call it:

```python
from my_service import MyService

client = MyService(api_key="my_api_key")
job = client.my_method(...)          # returns a job immediately, does not block
result = job.wait_for_result()       # typed result back
```

Need a one-off client without writing a file? Skip generation:

```python
from fastsdk import FastSDK

client = FastSDK().create_temporary_client("openapi.json", api_key="my_api_key")
```

## Jobs

Every endpoint call returns a job. Start many, collect them later.

```python
job = client.my_method(...)

job.wait_for_result()   # block until done, return the typed result
job.cancel()            # cancel locally if queued, or ask the provider to cancel
```

For job-based providers (APIPod, Runpod, Socaity, Replicate), fastSDK polls remote status and reports progress until the job reaches a terminal state.

## Files

File parameters accept paths or [media-toolkit](https://github.com/SocAIty/media-toolkit) objects. Large files upload to cloud storage ([Azure Blob](https://azure.microsoft.com/products/storage/blobs/), [Amazon S3](https://aws.amazon.com/s3/)) and are passed by URL; results come back as typed media objects you can save.

```python
from fastsdk import ImageFile

job = client.swap_img_to_img("face_1.jpg", "face_2.jpg")
result = job.wait_for_result()
result.save("swapped.jpg")
```

`MediaFile`, `ImageFile`, `VideoFile`, and `AudioFile` are importable straight from the package.

## API keys

Pass the key when you create the client, or read it from the environment:

```python
import os
from my_service import MyService

client = MyService(api_key=os.getenv("MY_API_KEY"))
```

## Service compatibility

Works out of the box with:

| Provider | Notes |
|----------|-------|
| OpenAPI 3.0 / REST | FastAPI, Flask, any compliant spec |
| [APIPod](https://github.com/SocAIty/APIPod) | job-based services |
| [Runpod](https://github.com/runpod/runpod-python) | serverless GPU endpoints |
| [Cog](https://github.com/replicate/cog) | Replicate-style services |
| [Socaity](https://www.socaity.ai) | hosted models |
| [Replicate](https://www.replicate.com) | prediction APIs |

## fastSDK and APIPod

<img src="https://github.com/SocAIty/APIPod/blob/main/docs/fastsdk_to_apipod.png?raw=true" width="50%" />

[APIPod](https://github.com/SocAIty/APIPod) builds and deploys the services. fastSDK calls them. Two halves of the same client-to-service loop, designed for long-running ML and data workloads.

## Architecture

For internals (definition layer, runtime pipeline, cancellation, how meseex fits in) see [TECHNICAL_README.md](TECHNICAL_README.md).

## Status

Alpha. Syntax and surface change rapidly. Bug reports, ideas, and pull requests are welcome in the issues section.

fastSDK is licensed under [GPLv3](LICENSE) and free to use. Leave a star to support us.
