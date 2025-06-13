from .api_client import APIClient, APIKeyError
from fastsdk.service_management.service_definition import SocaityServiceAddress


class APIClientSocaity(APIClient):
    def validate_api_key(self) -> bool:
        if not isinstance(self.service_def.service_address, SocaityServiceAddress) or "api.socaity.ai" not in self.service_address.url:
            return True
        if self.api_key is None:
            raise APIKeyError("API key is required for Socaity API.", "socaity", "https://www.socaity.ai/")
        if len(self.api_key) < 67 or not self.api_key.startswith("sk_"):
            raise APIKeyError("Invalid API key. It should look like 'sk_...'. ", "socaity", "https://www.socaity.ai/")
        return True
