from typing import Dict, Any, Optional, Union
import httpx

from fastsdk.service_definition import ServiceDefinition, EndpointDefinition
from fastsdk.service_interaction.response.base_response import BaseJobResponse
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
    """
    Handles all HTTP interactions with APIs.
    Manages HTTP clients, request preparation, sending, and polling.
    """
    def __init__(self, service_def: ServiceDefinition, api_key: str = None):
        self.__client = None
        self.service_def = service_def
        self.api_key = api_key
        self.validate_api_key()
        self.poll_method = "POST"
        
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
        """
        Add authorization headers to the request.
        
        Args:
            service_def: Service definition containing API key
            headers: Optional existing headers to add to
        
        Returns:
            Dictionary of headers with authorization added if available
        """
        headers = headers or {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_request_url(self, endpoint: EndpointDefinition, query_params: Dict = None) -> str:
        """
        Build the complete request URL with query parameters.
        
        Args:
            service_def: Service definition
            endpoint: Endpoint definition
            query_params: Query parameters to include in URL
            
        Returns:
            Complete URL
        """
        if not self.service_def.service_address:
            return None

        base_url = f"{self.service_def.service_address.url}/{endpoint.path.lstrip('/')}"
        if query_params:
            query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
            return f"{base_url}?{query_string}"
        return base_url

    def format_request_params(self, endpoint: EndpointDefinition, data: dict) -> RequestData:
        """
        Prepare all request parameters for the endpoint.
        Puts the parameters from data into the right location RequestData object.
        """
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
            
            is_file_param = False
            is_array_param = False
            if hasattr(param, "type") and param.type is not None:
                ptype = param.type if isinstance(param.type, list) else [param.type]
                is_file_param = any(t in ["file", "image", "video", "audio"] for t in ptype)
                is_array_param = any(t in ["array"] for t in ptype)

            # if is file type put it into file_params
            is_file_param = is_file_param or isinstance(param_value, MediaFile)

            if is_array_param and not isinstance(param_value, list):
                param_value = [param_value]

            if is_file_param:
                rq.file_params[param.name] = param_value
            if param.location == "query":
                rq.query_params[param.name] = param_value
            elif param.location == "body":
                rq.body_params[param.name] = param_value

        rq.url = self._build_request_url(endpoint, rq.query_params)
        rq.headers = self._add_authorization_to_headers(rq.headers)
        return rq

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
        # Use json parameter for JSON requests, data for form requests
        if request_data.file_params:
            # If there are files, use multipart/form-data
            return await self.client.post(
                url=request_data.url,
                params=request_data.query_params,
                data=request_data.body_params,
                files=request_data.file_params,
                headers=request_data.headers,
                timeout=timeout_s
            )
        
        # If no files, send as JSON. Important, if no files are present;
        return await self.client.post(
            url=request_data.url,
            params=request_data.query_params,
            json=request_data.body_params,  # Use json parameter instead of data
            headers=request_data.headers,
            timeout=timeout_s
        )

    async def request_url(
        self,
        url: str,
        method: str = "GET",
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Submit a direct URL request.
        
        Args:
            service_def: Service definition 
            url: Target URL
            method: HTTP method
            files: Optional files to upload
            timeout: Request timeout
            **kwargs: Additional request parameters
            
        Returns:
            The API response
        """
        if not url.startswith(("http://", "https://")):
            url = f"{self.service_def.service_address.url}/{url.lstrip('/')}"

        headers = self._add_authorization_to_headers()
        timeout = timeout or 60

        method = method.upper()
        if method == "GET":
            return await self.client.get(url=url, headers=headers, timeout=timeout, **kwargs)
        elif method == "POST":
            return await self.client.post(url=url, files=files, headers=headers, timeout=timeout, **kwargs)
        elif method == "PUT":
            return await self.client.put(url=url, files=files, headers=headers, timeout=timeout, **kwargs)
        elif method == "DELETE":
            return await self.client.delete(url=url, headers=headers, timeout=timeout, **kwargs)
        else:
            return await self.client.post(url=url, headers=headers, timeout=timeout, **kwargs)
            
    async def poll_status(self, response: Union[BaseJobResponse, Any], method: str = "POST") -> httpx.Response:
        """
        Poll for job completion.
        
        Args:
            service_def: Service definition
            response: Initial response from API which may be a job response
            
        Returns:
            Updated response or None to continue polling
        """
        # If not a job-based API response, return immediately
        if not isinstance(response, BaseJobResponse):
            return response
            
        # Request updated status
        return await self.request_url(
            url=response.refresh_job_url,
            method=self.poll_method
        )
        
