import json
import httpx
from fastsdk.service_interaction.request.api_client import APIClient, APIKeyError, RequestData
from fastsdk.service_management.service_definition import EndpointDefinition


class APIClientReplicate(APIClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_method = "GET"
        
    def validate_api_key(self):
        if self.api_key is None:
            raise APIKeyError("API key is required for Replicate API.", "replicate", "https://www.replicate.com/")
        
        if not self.api_key.startswith("r8_"):
            raise APIKeyError("Invalid API key. It should look like 'r8_...'. ", "replicate", "https://www.replicate.com/")

        return True
    
    def _build_request_url(self, endpoint: EndpointDefinition, query_params: dict | None = None) -> str:
        # Overwrites the default implementation, because /endpoint_route is not attached.
        # Also query_parameters are added to body not to url.
        # (replicate always just has 1 endpoint)
        return self.service_address.url
    
    def format_request_params(self, endpoint: EndpointDefinition, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Replicate API."""
        request_data = super().format_request_params(endpoint, *args, **kwargs)

        # Add version parameter for community models to get params to make predictions
        version = getattr(self.service_def.service_address, "version", None)
        if request_data.url and "/predictions" in request_data.url and version:
            request_data.body_params['version'] = version

        return request_data

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        # replicates expects query params to be in body also
        request_data.body_params.update(request_data.query_params)
        request_data.body_params.update(request_data.file_params)
        request_data.query_params = {}
        request_data.file_params = {}

        # replicate formats the body as json with {"input": body_params, "version?": model_version}
        request_data.body_params = json.dumps({"input": request_data.body_params})

        return await super().send_request(request_data, timeout_s)
