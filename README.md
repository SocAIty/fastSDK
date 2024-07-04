# Package is still in development. Leave a star to support us.

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
- Easy file upload, download thanks [to media-toolkit](https://github.com/SocAIty/media-toolkit)
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
    def add_reference_face(self, job, face_name: str, source_img: bytes, save: bool = True):
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

#  

## ServiceClient in detail
The purpose of a service client is to send request and retrieve responses from the server.
  ```python
from socaity_client import ServiceClient, SDKMaker

srvc_face2face = ServiceClient(
    service_url="localhost:8020/api",
    model_name="face2face",
    model_domain_tags=[ModelDomainTag.IMAGE, ModelDomainTag.AUDIO],
    model_tags=[ModelTag.FACE2FACE, ModelTag.IMAGE2IMAGE]
)

````

