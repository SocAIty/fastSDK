from typing import Any, Optional

import httpx
import json
from fastsdk.service_interaction.request.api_client import APIClient, APIKeyError, RequestData
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk.service_interaction.response.response_schemas import SocaityJobResponse
from apipod_registry.definitions.service_definitions import RunpodServiceAddress, EndpointDefinition


class APIClientRunpod(APIClient):
    def validate_api_key(self) -> bool:
        if not isinstance(self.service_def.service_address, RunpodServiceAddress): # pass for non officially hosted or localhost services
            return True
        if self.api_key is None:
            raise APIKeyError("API key is required for Runpod API.", "runpod", "https://www.runpod.io/")
        if not self.api_key.startswith("rpa_"):
            raise APIKeyError("Invalid API key. It should look like 'rpa_...'. ", "runpod", "https://www.runpod.io/")
        return True

    def _build_request_url(self, endpoint: EndpointDefinition, query_params: dict | None = None) -> str:
        # Overwrites the default implementation, because query parameters are not added to the url but to the body
        url = self.service_def.service_address.url.strip("/")  # don't use strip("/run") it will remove the letters / r u and n.
        if url.endswith("/run"):
            url = url[:-4]  # Remove "/run" suffix
        return f"{url}/run"

    def get_poll_url(self, response) -> Optional[str]:
        return f"status/{response.id}"

    def get_cancel_url(self, response) -> Optional[str]:
        return f"cancel/{response.id}"

    def get_result(self, response) -> Any:
        return getattr(response, "output", None)

    def format_request_params(self, endpoint: EndpointDefinition, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Runpod API."""
        request_data = super().format_request_params(endpoint, *args, **kwargs)

        # adding path to the body for runpod apipod services
        if endpoint.path:
            request_data.body_params["path"] = endpoint.path

        return request_data

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        """
        Send the prepared request to the API.
        """
        # runpod wants all parameters in the body. If it is a an apipod service the "path" is in the body.
        # so we need to check if the service is a apipod service and if so, we need to add the path to the body.
        
        all_params = request_data.body_params
        all_params.update(request_data.query_params)
        all_params.update(request_data.file_params)

        request_data.file_params = {}
        request_data.query_params = {}
        request_data.body_params = json.dumps({"input": all_params})

        return await self.client.post(
            url=request_data.url,
            data=request_data.body_params,
            headers=request_data.headers,
            timeout=timeout_s
        )


class APIClientRunpodApipod(APIClientRunpod):
    """Runpod transport for initial request, Socaity-style polling once
    the nested APIPod payload appears in the output.

    The parser returns ``SocaityJobResponse`` when the nested payload is
    found, and ``RunpodJobResponse`` while still queued.  This client
    adapts its behaviour based on which type it receives.
    """

    def get_poll_url(self, response) -> Optional[str]:
        if isinstance(response, SocaityJobResponse):
            return response.links.status if response.links else None
        return super().get_poll_url(response)

    def get_cancel_url(self, response) -> Optional[str]:
        if isinstance(response, SocaityJobResponse):
            return response.links.cancel if response.links else None
        return super().get_cancel_url(response)

    def get_result(self, response) -> Any:
        if isinstance(response, SocaityJobResponse):
            return response.result
        return super().get_result(response)

    def get_status(self, response) -> APIJobStatus:
        if isinstance(response, SocaityJobResponse):
            return APIJobStatus.from_str(response.status)
        return super().get_status(response)

    async def poll_status(self, response) -> httpx.Response:
        url = self.get_poll_url(response)
        if not url:
            raise ValueError("No polling URL available")
        method = "GET" if isinstance(response, SocaityJobResponse) else self.poll_method
        return await self.request_url(url=url, method=method)
