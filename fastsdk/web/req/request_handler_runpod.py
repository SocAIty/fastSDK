import json
from typing import Union

from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.req.request_handler import RequestHandler


class RequestHandlerRunpod(RequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # replicate expects the files to be in base64 format in the input post parameter.
        # setting the value changes the behavior of the _upload_files method
        self._attached_files_format = 'base64'

    def _prepare_request_url(self, endpoint: EndPoint, query_params: dict = None) -> str:
        # Overwrites the default implementation, because query parameters are not added to the url but to the body
        return f"{self.service_address.url}/run"

    async def _request_endpoint(
            self,
            url: Union[str, None],
            query_params: Union[dict, None],
            body_params: Union[dict, None],
            file_params: Union[dict, None],
            headers: Union[dict, None],
            timeout: float,
            endpoint: EndPoint
    ):
        # Performing a request to the runpod or fast-task-api endpoint with given path
        # path might have double arguments. Cleaning it.
        path = endpoint.endpoint_route.lstrip("/").lstrip("run/")
        body_params["path"] = path
        # every other param goes into the body_params
        if query_params is not None:
            body_params.update(query_params)
        if file_params:
            body_params.update(file_params)

        # runpod expects input data to be in a json object with the key "input"
        data = json.dumps({"input": body_params})
        return await self.httpx_client.post(url=url, data=data, headers=headers, timeout=timeout)


