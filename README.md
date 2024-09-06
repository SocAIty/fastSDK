
<h1 align="center" style="margin-top:-25px">fastSDK</h1>
<p align="center">
  <img align="center" src="docs/fastsdk_logo.png" height="256" />
</p>
<h3 align="center" style="margin-top:-10px">Built your SDK for any hosted service</h3>



Ever wanted to use web APIs as if they are any other python function?
It was never easier to build an SDK for your hosted services, than it is with socaity-client.

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
- OpenAPI 3.0 / RestAPIs
  - [fastAPI](https://github.com/tiangolo/fastapi)
  - [Flask](https://flask.palletsprojects.com/en/2.0.x/)
- [Runpod](https://github.com/runpod/runpod-python) services

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
Including cloud storage providers: This allows you to upload bigger filed to common cloud storage providers.
```bash
pip install fastsdk[full] #  full feature support
pip install fastsdk[azure]  # only azure blob storage support
pip install fastsdk[s3] #only  s3 upload
```


# Get started

To build your SDK for a web API follow these steps:
1. Create a ```ServiceClient``` with the base url of the service and the endpoint routes.
2. Use the ```@fastSDK``` and ```@fastJob``` decorators around the service client to create your SDK.

Create the service client - the object that sends the requests to the server.
```python
from fastsdk import ServiceClient, ImageFile

# 1. create a service client
srvc_face2face = ServiceClient(service_url="localhost:8020/api")
# on a request the module will try to cast the parameters to the specified types
srvc_face2face.add_endpoint(
    endpoint_route="add_face",
    post_params={"face_name": str},
    file_params={"img": ImageFile} 
)
```
Based on the service we create the SDK by using the smart decorators ```@fastSDK``` and ```@fastJob```.
The ```@fastSDK``` decorator will create a class with the service client as a class attribute.

The ```@fastJob``` decorator allows your functions to:
- be called asynchronously and in a separate thread.
- be called with a *job* object which can be used to send requests to the service endpoint.

Let's create the SDK for the service client.
````python
from fastsdk import fastSDK, fastJob
@fastSDK(service_client=srvc_face2face)
class face2face:
  @fastJob
  def _add_face(self, job: InternalJob, face_name: str, source_img: bytes, save: bool = True):
        # send the request to the service endpoint using the provided job object
        endpoint_request = job.request("add_reference_face", face_name, source_img, save)
        # wait until server finished the job
        result = endpoint_request.get_result() 
        return result
````
Add this point your SDK is ready and now you can work with it as follows
```python
f2f = face2face()
# start the request in a seperate thread
# Note that the job object is not passed to the kwargs. The wrapper will handle this for us.
ref_face_v_job = f2f.add_face(face_name="potter", img="path/to/image/of/harry")
# do something else... this works becauce ref_face_v_job will start a thread
ref_face_vector = ref_face_v_job.get_result() # wait for the server and thread to finish the job
```


## Cloud storage providers and file uploads

The SDK comes with a built-in support for cloud storage providers like Amazon S3 and Azure Blob Storage.
To directly up and download files to the cloud storage provider, you can use the following code snippets.
```python 
from fastsdk import AzureBlobStorage
# Create container and upload file
container = AzureBlobStorage(sas_access_token)
file_url = container.upload(file="path/to/file")
# Use media-toolkit to download file
file = MediaFile.from_url(container.download(file_id))
```


### File size limited file uploads
Let's say you built an SDK for a service which works with files > 10mb.
In a usual workflow the client will upload the file to a storage provider and then send the file id to the service.
Instead of implementing this from hand, you can use the SDK to handle the file uploads for you.

```python
from fastsdk import create_cloud_storage, ServiceClient

cs = create_cloud_storage(azure_sas_access_token=AZURE_SAS_ACCESS_TOKEN,
                          azure_connection_string=AZURE_SAS_CONNECTION_STRING)
srvc_face2face = ServiceClient(cloud_storage=cs, upload_to_cloud_storage_threshold_mb=10)
```
In this case every file > 10mb will be uploaded to the cloud storage provider. 
Then instead of the file, the file_url will be send to the service.
If the file size is smaller than 10mb, the file will be send directly to the service as bytes.
The MediaToolkit knows how to handle the file_url and will download the file for you in the service.

Recommendation: Use environment variables to store the cloud storage access tokens.

## ServiceClient in detail
The purpose of a service client is to send request and retrieve responses from the server.
  ```python
from socaity_client import ServiceClient, FastSDK

srvc_face2face = ServiceClient(
    service_url="localhost:8020/api",
    model_name="face2face",
    model_domain_tags=[ModelDomainTag.IMAGE, ModelDomainTag.AUDIO],
    model_tags=[ModelTag.FACE2FACE, ModelTag.IMAGE2IMAGE]
)

```

### Authorization
Let's say you have created your SDK with ```@fastSDK``` and named it face2face
Then you can init it with arguments. In this moment you can pass the api key.
```python
f2f = face2face(service_name="runpod", api_key="my_api_key")
```
Alternatively you can set the api_keys in the settings and give them names like "runpod".
Add this at the beginning of your script.

```python
import os
import settings
settings.api_keys["runpod"] = os.getenv("my_api_key")
# Then you can init the service client without the api_key argument at any place.
f2f = face2face(service_name="runpod")
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