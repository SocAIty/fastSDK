# FastSDK: Built your SDK for any hosted service

Ever wanted to use web APIs as if they are any other python function?
It was never easier to build an SDK for your hosted services, than it is with socaity-client.

Out of the box works with following services:
- Services created with [FastTaskAPI](https://github.com/SocAIty/socaity-router) which return a job object.
- OpenAPI 3.0 / RestAPIs
  - [fastAPI](https://github.com/tiangolo/fastapi)
  - [Flask](https://flask.palletsprojects.com/en/2.0.x/)
- [Runpod](https://github.com/runpod/runpod-python) services

Features:
- Easy file upload, download thanks [to media-toolkit](https://github.com/SocAIty/media-toolkit). 
- Support for cloud storage providers like Amazon S3 and Azure Blob Storage.
- Streaming of files 
- Automatic serialization of data types
- Async and Threaded job supports. -> Max speed!
- Working with services that create "Jobs". -> the SDK will wait for the job to finish and return the result.
  - Retrieving the job status and printing status updates.

# Get started

To integrate a webservice you need to follow two steps:
1. Instantiate a service client with the base url of the service and the endpoint routes.
2. Use the SDK maker around the service client to create a SDK.

First we create the service client - the object that sends the requests to the server.
```python
from fastsdk import FastSDK, ServiceClient, ImageFile

# 1. create a service client
srvc_face2face = ServiceClient(service_url="localhost:8020/api")
# on a request the module will try to cast the parameters to the specified types
srvc_face2face.add_endpoint(
    endpoint_route="add_reference_face",
    post_params={"face_name": str},
    file_params={"source_img": ImageFile} 
)
```
Based on the service we create the SDK
````python
# this is already a usable SDK
face2face_sdk = FastSDK(srvc_face2face) 
# however, we prettify the imports to provide a nice interface for follow up developers
class face2face:
    # this decorator gives your SDK method a job object to work with. 
    # and the method is threaded when called.
    @face2face_sdk.job() 
    def add_face(self, job, face_name: str, source_img: bytes, save: bool = True):
        # send the request to the service endpoint
        endpoint_request = job.request("add_reference_face", face_name, source_img, save)
        # wait until server finished the job
        result = endpoint_request.get_result() 
        return result
````
Add this point your SDK is ready and now you can work with it as follows
```python
f2f = face2face()
# start the request in a seperate thread
ref_face_v_job = f2f.add_reference_face("potter", "path/to/image/of/harry", save=True)
# do something else... this works becauce ref_face_v_job will start a thread
ref_face_vector = ref_face_v_job.get_result() # wait for the server and thread to finish the job
```




## Cloud storage providers and file uploads

The SDK comes with a built-in support for cloud storage providers like Amazon S3 and Azure Blob Storage.
To directly up and download files to the cloud storage provider, you can use the following code snippets.
```python 
from fastsdk import AzureBlobStorage
# Create container and upload file
container = AzureBlobStorage(sas_url_admin)
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
API keys can be set in environment variables, when creating the Service Client or when initializing your SDK.
In settings.py the default environment variables are set.

```python
f2f = face2face(service_name="runpod", api_key="my_api_key")
```

