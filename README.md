
# Readme coming soon...


# FastSDK: Built your SDK for any hosted service

Ever wanted to use web APIs as if they are any other python function?
It was never easier to build an SDK for your hosted services, than it is with socaity-client.

Out of the box works with following services:
- Services created with [FastTaskAPI](https://github.com/SocAIty/socaity-router) which return a job object.
- OpenAPI 3.0 / RestAPIs
  - [fastAPI](https://github.com/tiangolo/fastapi)
  - [Flask](https://flask.palletsprojects.com/en/2.0.x/)
- [Runpod](https://github.com/runpod/runpod-python) services


# Get started

To integrate an webservice you need to follow two steps:
1. Instantiate a service client with the base url of the service and the endpoint routes.
2. Use the SDK maker with the service
