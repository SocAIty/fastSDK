from typing import Dict, Any, Optional, Union
import httpx
from urllib.parse import urlencode

from apipod_registry.definitions.service_definitions import ServiceDefinition, EndpointDefinition
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from media_toolkit import MediaFile


class APIKeyError(Exception):
    """Custom exception for API key validation errors."""
    def __init__(self, message: str, service_name: str, signup_url: str):
        message = f"{message}\nPlease create an account at {signup_url} and get an API key. Set the API key using environment variable {service_name.upper()}_API_KEY."
        super().__init__(message)


class RequestData:
    def __init__(self, query_params: dict = {}, body_params: dict = {}, file_params: Union[dict, Any, None] = {}, headers: dict = {}, url: str = ""):
        self.query_params = query_params or {}
        self.body_params = body_params or {}
        self.file_params = file_params or {}
        self.headers = headers or {}
        self.url = url


class APIClient:
    """Handles all HTTP interactions with APIs.

    Subclasses override the ``get_*`` accessors to teach the base
    ``poll_status`` / ``cancel_job`` methods how to extract URLs and
    status from their provider-specific response models.
    """

    def __init__(self, service_def: ServiceDefinition, api_key: str = None):
        self.__client = None
        self.service_def = service_def
        self.api_key = api_key
        self.validate_api_key()
        self.poll_method = "POST"
        self.cancel_method = "POST"

    # ------------------------------------------------------------------
    # Provider-specific accessors (override in subclasses)
    # ------------------------------------------------------------------

    def get_status(self, response) -> APIJobStatus:
        return APIJobStatus.from_str(getattr(response, "status", None))

    def get_poll_url(self, response) -> Optional[str]:
        return None

    def get_cancel_url(self, response) -> Optional[str]:
        return None

    def get_result(self, response) -> Any:
        return getattr(response, "result", None)

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    @property
    def client(self) -> httpx.AsyncClient:
        if self.__client is None or self.__client.is_closed:
            self.__client = httpx.AsyncClient()
        return self.__client

    def validate_api_key(self) -> bool:
        """
        Override this method to validate the API key for specific providers.
        Returns True if the API key is valid.
        Raises APIKeyError if the API key is invalid.
        """
        return True

    def _add_authorization_to_headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = headers or {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_request_url(self, endpoint: EndpointDefinition, query_params: Dict = None) -> str:
        if not self.service_def.service_address:
            return None
        base_url = self.service_def.service_address.build_endpoint_url(endpoint.path)
        if query_params:
            query_string = urlencode(query_params, doseq=True)
            return f"{base_url}?{query_string}"
        return base_url

    def format_request_params(self, endpoint: EndpointDefinition, data: dict) -> RequestData:
        """Prepare all request parameters for the endpoint."""
        if not data:
            rq = RequestData()
            rq.headers = self._add_authorization_to_headers()
            rq.url = self._build_request_url(endpoint, rq.query_params)
            return rq

        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        rq = RequestData()
        for param in endpoint.parameters:
            param_value = data.get(param.name, param.default)
            if param_value is None and param.required:
                raise ValueError(f"Required parameter '{param.name}' is missing")
            
            # Determine characteristics
            is_file_param = False
            is_array_param = False

            # Detect media/file by ParameterDefinition.format
            definitions = getattr(param, "definition", None)
            if definitions is not None:
                defs = definitions if isinstance(definitions, list) else [definitions]
                for d in defs:
                    if getattr(d, "format", None) in {"file", "image", "video", "audio"}:
                        is_file_param = True
                        break

            # Detect array via schema
            schema = getattr(param, "param_schema", None) or {}
            if isinstance(schema, dict) and schema.get("type") == "array":
                is_array_param = True

            # if is file type put it into file_params
            is_file_param = is_file_param or isinstance(param_value, MediaFile)

            if is_array_param and not isinstance(param_value, list):
                param_value = [param_value]

            if is_file_param:
                rq.file_params[param.name] = param_value
            elif param.location == "query":
                rq.query_params[param.name] = param_value
            elif param.location == "body":
                rq.body_params[param.name] = param_value

        rq.url = self._build_request_url(endpoint, rq.query_params)
        rq.headers = self._add_authorization_to_headers(rq.headers)
        return rq

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        """Send the prepared request to the API with streaming support."""
        kwargs = {
            "url": request_data.url,
            "params": request_data.query_params,
            "headers": request_data.headers,
            "timeout": timeout_s
        }

        if request_data.file_params:
            # If there are files, use multipart/form-data (data=)
            kwargs["data"] = request_data.body_params
            kwargs["files"] = request_data.file_params
        else:
            # If no files, send as JSON (json=)
            kwargs["json"] = request_data.body_params

        # Use build_request + send(stream=True) to support direct SSE responses
        request = self.client.build_request("POST", **kwargs)
        return await self.client.send(request, stream=True)

    async def request_url(
        self,
        url: str,
        method: str = "GET",
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> httpx.Response:
        """Submit a direct URL request with streaming support."""
        if not self.service_def.service_address:
            raise ValueError("Service address is required to request a relative URL")

        url = self.service_def.service_address.resolve_url(url)
        headers = self._add_authorization_to_headers()
        timeout = timeout or 60

        request = self.client.build_request(
            method=method, 
            url=url, 
            files=files, 
            headers=headers, 
            timeout=timeout, 
            **kwargs
        )
        return await self.client.send(request, stream=True)

    async def poll_status(self, response) -> httpx.Response:
        url = self.get_poll_url(response)
        if not url:
            raise ValueError("No polling URL available for this response")
        return await self.request_url(url=url, method=self.poll_method)

    async def cancel_job(self, response) -> httpx.Response:
        url = self.get_cancel_url(response)
        if not url:
            raise ValueError("No cancel URL available for this response")
        return await self.request_url(url=url, method=self.cancel_method)
