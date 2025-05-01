from fastsdk.client.definitions.service_adress import SocaityServiceAddress
from fastsdk.client import RequestHandler, RequestData, APIKeyError, EndPoint


class RequestHandlerSocaity(RequestHandler):
    """
    Works with Socaity API: https://api.socaity.ai/docs
    """
    def validate_api_key(self):
        # pass for non officially hosted or localhost services
        if not isinstance(self.service_address, SocaityServiceAddress) or "api.socaity.ai" not in self.service_address.url:
            return True

        if self.api_key is None:
            raise APIKeyError("API key is required for Socaity API.", "socaity", "https://www.socaity.ai/")

        if len(self.api_key) != 67 or not self.api_key.startswith("sk_"):
            raise APIKeyError("Invalid API key. It should look like 'sk_...'. ", "socaity", "https://www.socaity.ai/")
        return True

    async def _prepare_request_params(self, endpoint: EndPoint, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Replicate API."""
        request_data = await super()._prepare_request_params(endpoint, *args, **kwargs)

        # socaity expects query params to be in body also
        if request_data.query_params:
            request_data.body_params.update(request_data.query_params)
            request_data.query_params = {}

        return request_data
