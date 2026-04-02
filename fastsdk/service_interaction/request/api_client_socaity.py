from .api_client import APIClient, APIKeyError, RequestData
from apipod_registry.definitions.service_definitions import SocaityServiceAddress
import httpx

class APIClientSocaity(APIClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_method = "GET"

    def validate_api_key(self) -> bool:
        service_address = self.service_def.service_address
        if not isinstance(service_address, SocaityServiceAddress) or "api.socaity.ai" not in service_address.base_url:
            return True
        if self.api_key is None:
            raise APIKeyError("API key is required for Socaity API.", "socaity", "https://www.socaity.ai/")
        if not self.api_key.startswith(("sk_", "tk_")) or len(self.api_key) < 10:
            raise APIKeyError("Invalid API key. It should look like 'sk_...' or 'tk_...'.", "socaity", "https://www.socaity.ai/")
        return True

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        """
        Socaity/APIPod services expect multipart/form-data when files are
        present, but plain JSON otherwise. Supports direct streaming responses.
        """
        kwargs = {
            "url": request_data.url,
            "params": request_data.query_params,
            "headers": request_data.headers,
            "timeout": timeout_s
        }

        if request_data.file_params:
            # Multipart form-data when files are attached
            kwargs["data"] = request_data.body_params
            kwargs["files"] = request_data.file_params
        else:
            # JSON body when there are no file attachments
            kwargs["json"] = request_data.body_params

        request = self.client.build_request("POST", **kwargs)
        return await self.client.send(request, stream=True)
