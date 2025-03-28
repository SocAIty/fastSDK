import json
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.req.request_handler import RequestHandler, RequestData, APIKeyError
from media_toolkit import MediaDict


class RequestHandlerRunpod(RequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Runpod expects the files to be in base64 format in the input post parameter.
        # setting the value changes the behavior of the _upload_files method
        self._attached_files_format = 'base64'

    def validate_api_key(self):
        if self.api_key is None:
            raise APIKeyError("API key is required for using runpod services.", "runpod", "https://www.runpod.com/")
        return True

    def _prepare_request_url(self, endpoint: EndPoint, query_params: dict | None = None) -> str:
        # Overwrites the default implementation, because query parameters are not added to the url but to the body
        return f"{self.service_address.url}/run"

    async def _prepare_request_params(self, endpoint: EndPoint, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Runpod API."""
        request_data = await super()._prepare_request_params(endpoint, *args, **kwargs)

        # Convert file_params to MediaDict if needed
        if request_data.file_params and not isinstance(request_data.file_params, MediaDict):
            request_data.file_params = MediaDict(request_data.file_params, download_files=False)

        # Process files using base handler logic (will convert to base64)
        body_files, _ = await self._prepare_files(request_data.file_params)
        request_data.body_params.update(body_files)

        # Performing a request to the runpod or fast-task-api endpoint with given path
        # path might have double arguments. Cleaning it.
        path = endpoint.endpoint_route.lstrip("/").lstrip("run/")
        request_data.body_params["path"] = path
        # every other param goes into the body_params
        if request_data.query_params is not None:
            request_data.body_params.update(request_data.query_params)

        request_data.body_params = json.dumps(request_data.body_params)

        return request_data
