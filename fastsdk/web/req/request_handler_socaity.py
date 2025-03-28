from io import BytesIO
from typing import Union, Tuple, Dict, Any

from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.service_adress import SocaityServiceAddress
from fastsdk.web.req.request_handler import RequestHandler, RequestData
from media_toolkit import MediaFile, MediaList, MediaDict


class APIKeyError(Exception):
    """Custom exception for API key validation errors."""
    def __init__(self, message: str):
        message = f"{message}\nPlease create an account at https://www.socaity.ai/ and get an API key. Set the API key using environment variable SOCAITY_API_KEY."
        super().__init__(message)


class RequestHandlerSocaity(RequestHandler):
    """
    Works with Socaity API: https://api.socaity.ai/docs
    """
    def validate_api_key(self):
        # pass for non officially hosted or localhost services
        if not isinstance(self.service_address, SocaityServiceAddress) or "api.socaity.ai" not in self.service_address.url:
            return True

        if self.api_key is None:
            raise APIKeyError("API key is required for Socaity API.")

        if len(self.api_key) != 67 or not self.api_key.startswith("sk_"):
            raise APIKeyError("Invalid API key. It should look like 'sk_...'. ")
        return True

    async def _prepare_request_params(self, endpoint: EndPoint, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Socaity API."""
        request_data = await super()._prepare_request_params(endpoint, *args, **kwargs)
        
        # Convert file_params to MediaDict if needed
        if file_params and not isinstance(file_params, MediaDict):
            request_data.file_params = MediaDict(request_data.file_params, download_files=False)
            
        # Process files using base handler logic
        body_files, file_params = await self._prepare_files(request_data.file_params)
        request_data.body_params.update(body_files)

        return request_data

