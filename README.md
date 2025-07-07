
<h1 align="center" style="margin-top:-25px">fastSDK</h1>
<p align="center">
  <img align="center" src="docs/fastsdk_logo.png" height="256" />
</p>
<h3 align="center" style="margin-top:-10px">Built your SDK for any hosted service</h3>



Ever wanted to use web APIs as if they are any other python function?
It was never easier to build an SDK for your hosted services, than it is with fastSDK.
FastSDK creates a full functioning client for any openapi service.

### Why?

Let's say you have created a webservice for example with [fastAPI](https://github.com/tiangolo/fastapi) or [flask](https://github.com/pallets/flask) and now you want to write a python client for it.
In a first approach you would just use the [requests](https://pypi.org/project/requests/) library and send the requests to the server. However, while you do so,
your cpu is idle waiting for the request to finish. Over time your requirements get bigger, suddenly you do not only have one endpoint but multiples.
You will do different requests in parallel, you need to transfer files, and you struggle to do so in a structured, performant way. 
Suddenly you end up in a threading, asyncio and complexity hell with many inconsistencies. You realize that you cannot transfer your 1GB video via an simple web request to your beautiful API.
All these problems are solved with the fastSDK.
Simple API calls, file uploads, job handling, and cloud storage providers are just a few features of the fastSDK.

FastSDK is designed to work beautifully with long-running services like machine learning and data processing endpoints.
It works hand-in-hand with [FastTaskAPI](https://github.com/SocAIty/FastTaskAPI) that let's you build and deploy those services and endpoints easily.

### Service compatibility

Out of the box works with following services:
- Services created with [FastTaskAPI](https://github.com/SocAIty/FastTaskAPI) which return a job object.
- [Runpod](https://github.com/runpod/runpod-python) services
- [Cog](https://github.com/replicate/cog) services
- OpenAPI 3.0 / RestAPIs
  - [fastAPI](https://github.com/tiangolo/fastapi)
  - [Flask](https://flask.palletsprojects.com/en/2.0.x/)

Can be used together with
- [Socaity.ai](https://www.socaity.ai) services 
- [Replicate.ai](https://www.replicate.com) services

### Features:
- Easy file upload, download thanks to [media-toolkit](https://github.com/SocAIty/media-toolkit). 
  - Support for cloud storage providers like  [Azure Blob Storage](https://azure.microsoft.com/de-de/products/storage/blobs/?msockid=015b54a7ada76c452812402bac8c6dde) and [Amazon S3](https://aws.amazon.com/es/s3/).
- Async and Threaded job support. Execute multiple requests and heavy preprocessing tasks in parallel and with high speed.
  - Massively parallel job and request execution.
- Working with services that create "Jobs". The SDK will wait for the job to finish and return the result.
  - Support for [FastTaskAPI](https://github.com/SocAIty/FastTaskAPI) and [runpod (serverless)](https://www.runpod.io/serverless-gpu) endpoints.
  - Retrieving the job status, progres and print status updates.
- Streaming of files 
- Automatic serialization of data types

# Installation

To install from PyPI:
This version includes all features needed to conveniently wrap your API into an SDK.
```bash
pip install fastsdk
```

# Get started

First get your openapi.json file from your service usully under:  [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json).
You can use an example openapi.json from our face2face service located in this repos under [/test/test_files/face2face.json](/test/test_files/face2face.json)

```python
# create a full working client stub 
create_sdk("openapi.json", save_path="my_service.py")

# Import the client. It will have a method for each of your service endpoints including all parameters and its default values.
from my_service import awesome_client
mySDK = awesome_client()
mySDK.my_method(...)
```

### Authorization
Let's say you have created your SDK (client) with ```@fastSDK``` and named it face2face
Then you can init it with arguments. In this moment you can pass the api key.
```python
f2f = face2face(api_key="my_api_key")
api_job = f2f.swap_img_to_img(source_img="my_face_1.jpg", target_img="my_face_2.jpg")
swapped_img = api_job.get_result()
```
Alternatively you can set the api_keys in the settings and give them names like "runpod".
Add this at the beginning of your script.

```python
import os
import settings
settings.api_keys["runpod"] = os.getenv("my_api_key")
``` 

API keys can be set in environment variables, when creating the Service Client or when initializing your SDK.
In settings.py the default environment variables are set.

# FastSDK :two_hearts: FastTaskAPI

<img src="https://github.com/SocAIty/FastTaskAPI/blob/main/docs/fastsdk_to_fasttaskapi.png?raw=true" width="50%" />

[FastTaskAPI](https://github.com/SocAIty/FastTaskAPI) allows you to easily create and deploy services that can be used with fastSDK.
They are two beating hearts :two_hearts: beating in harmony for client <--> service interaction.
Create your service now.

# Contribute

We at socaity want to provide the best tools to bring generative AI to the cloud.
Please report bugs, your ideas and feature requests in the issues section.
fastSDK is licensed under the MIT license and free-to-use.

## Note: THE PACKAGE IS STILL IN DEVELOPMENT!
#### LEAVE A STAR TO SUPPORT US. ANY BUG REPORT OR CONTRIBUTION IS HIGHLY APPRECIATED.
