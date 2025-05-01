import json
import httpx
from fastsdk.service_interaction.request.api_client import APIClient, APIKeyError, RequestData
from fastsdk.service_management.service_definition import EndpointDefinition, RunpodServiceAddress


class APIClientRunpod(APIClient):
    def validate_api_key(self) -> bool:
        if not isinstance(self.service_def.service_address, RunpodServiceAddress): # pass for non officially hosted or localhost services
            return True
        
        if self.api_key is None:
            raise APIKeyError("API key is required for Runpod API.", "runpod", "https://www.runpod.io/")
        if not self.api_key.startswith("r8_"):
            raise APIKeyError("Invalid API key. It should look like 'r8_...'. ", "runpod", "https://www.runpod.io/")
        return True

    def _build_request_url(self, endpoint: EndpointDefinition, query_params: dict | None = None) -> str:
        # Overwrites the default implementation, because query parameters are not added to the url but to the body
        return f"{self.service_def.service_address.url}/run"

    def format_request_params(self, endpoint: EndpointDefinition, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Runpod API."""
        request_data = super().format_request_params(endpoint, *args, **kwargs)

        # adding path to the body for runpod fasttaskapi services 
        if endpoint.path:
            request_data.body_params["path"] = endpoint.path

        return request_data

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        """
        Send the prepared request to the API.
        """
        # runpod wants all parameters in the body. If it is a an fasttaskapi service the "path" is in the body.
        # so we need to check if the service is a fasttaskapi service and if so, we need to add the path to the body.
        
        all_params = request_data.body_params
        all_params.update(request_data.query_params)
        all_params.update(request_data.file_params)

        request_data.file_params = {}
        request_data.query_params = {}
        request_data.body_params = json.dumps({"input": all_params})

        return await super().send_request(request_data, timeout_s)

