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

```python
from socaity_client import ServiceClient, SDKMaker

````

# 1. Create a service client
This allows you to send request and retrieve responses from the server.
  

# Threading and Async




## Package is still in development. Leave a star to support us.