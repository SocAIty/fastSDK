from .api_client import APIClient, APIKeyError
from fastsdk.service_management.service_definition import SocaityServiceAddress
import httpx
from fastsdk.service_interaction.request.api_client import RequestData

    
class APIClientSocaity(APIClient):
    def validate_api_key(self) -> bool:
        if not isinstance(self.service_def.service_address, SocaityServiceAddress) or "api.socaity.ai" not in self.service_address.url:
            return True
        if self.api_key is None:
            raise APIKeyError("API key is required for Socaity API.", "socaity", "https://www.socaity.ai/")
        if len(self.api_key) < 67 or not self.api_key.startswith("sk_"):
            raise APIKeyError("Invalid API key. It should look like 'sk_...'. ", "socaity", "https://www.socaity.ai/")
        return True

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        """
        Send the prepared request to the API.

        Args:
            service_def: Service definition
            request_data: The prepared request data
            timeout_s: Request timeout in seconds

        Returns:
            The API response
        """
        # Socaity expects data as multipart/form-data. Thus parameters are put into data and files.
        return await self.client.post(
            url=request_data.url,
            params=request_data.query_params,
            data=request_data.body_params,
            files=request_data.file_params,
            headers=request_data.headers,
            timeout=timeout_s
        )
