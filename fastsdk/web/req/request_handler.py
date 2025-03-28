import httpx
from pydantic import BaseModel
from typing import Optional, Union

from fastCloud import FastCloud
from fastCloud.core import BaseUploadAPI
from fastsdk.jobs.async_jobs.async_job import AsyncJob
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.service_adress import ServiceAddress, create_service_address
from media_toolkit import MediaDict


class APIKeyError(Exception):
    """Custom exception for API key validation errors."""
    def __init__(self, message: str, service_name: str, signup_url: str):
        message = f"{message}\nPlease create an account at {signup_url} and get an API key. Set the API key using environment variable {service_name.upper()}_API_KEY."
        super().__init__(message)


class RequestData:
    def __init__(self, query_params: dict = {}, body_params: dict = {}, file_params: Union[dict, any, None] = None, headers: dict = {}, url: str = ""):
        self.query_params = query_params
        self.body_params = body_params
        self.file_params = file_params
        self.headers = headers
        self.url = url


class RequestHandler:
    def __init__(
            self,
            service_address: str | ServiceAddress,
            async_job_manager: AsyncJobManager | None = None,
            api_key: str | None = None,
            fast_cloud: FastCloud | None = None,
            upload_to_cloud_threshold_mb: float = 3,
            max_upload_file_size_mb: float = 1000,
            *args, **kwargs
    ):
        """
        Initialize the RequestHandler with service configuration and file handling settings.

        Args:
            service_address: URL or ServiceAddress object for the target service
            async_job_manager: Optional AsyncJobManager for handling async operations
            api_key: Optional API key for authentication
            fast_cloud: Optional cloud storage handler for large file uploads
            upload_to_cloud_threshold_mb: File size threshold (MB) for cloud upload
            max_upload_file_size_mb: Maximum allowed file size (MB)
        """
        self.service_address = create_service_address(service_address) if not isinstance(service_address, ServiceAddress) else service_address
        self.api_key = api_key
        self.validate_api_key()
        self.async_job_manager = async_job_manager or AsyncJobManager()
        self.httpx_client = httpx.AsyncClient()

        # File handling configuration
        self.fast_cloud = fast_cloud
        self.upload_to_cloud_threshold_mb = upload_to_cloud_threshold_mb
        self.max_upload_file_size_mb = max_upload_file_size_mb
        self._attached_files_format = 'httpx'

    def validate_api_key(self):
        """
        Validates the api key. Override this method to add custom api key validation.
        :raises APIKeyError: If the api key is invalid.
        """
        return True

    def set_fast_cloud(
        self,
        fast_cloud: FastCloud,
        upload_to_cloud_threshold_mb: Optional[float] = None,
        max_upload_file_size_mb: Optional[float] = None
    ):
        """Update cloud storage configuration."""
        self.fast_cloud = fast_cloud
        self.upload_to_cloud_threshold_mb = upload_to_cloud_threshold_mb
        self.max_upload_file_size_mb = max_upload_file_size_mb

    @staticmethod
    def _format_params(p_def: Union[BaseModel, dict], *args, **kwargs) -> dict:
        """
        Format request parameters according to the endpoint definition.

        Args:
            p_def: Parameter definition (Pydantic model or dict)
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Formatted parameter dictionary
        """
        if p_def is None:
            return {}

        if isinstance(p_def, BaseModel):
            base_model_class = type(p_def)
            # match *args with model_fields
            _named_args = {k: v for k, v in zip(base_model_class.model_fields.keys(), args)}
            _named_args.update(kwargs)
            # validate the model_hosting_info with the given args and kwargs
            get_params = base_model_class.model_validate(_named_args)
            # return as dict
            return get_params.dict(exclude_unset=True)

        named_args = {k: v for k, v in zip(p_def, args)}
        named_args.update(kwargs)
        # filter out the parameters that are not in the endpoint definition
        return {k: v for k, v in named_args.items() if k in p_def}

    def _add_authorization_to_headers(self, headers: dict | None = None) -> dict | None:
        """Add authorization header if API key is present."""
        headers = {} if headers is None else headers
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers if headers else None

    async def _format_request_params(self, endpoint: EndPoint, *args, **kwargs) -> RequestData:
        """Prepare all request parameters for the endpoint."""
        query_params = self._format_params(endpoint.query_params, *args, **kwargs)
        body_params = self._format_params(endpoint.body_params, *args, **kwargs)
        file_params = self._format_params(endpoint.file_params, *args, **kwargs)
        headers = self._add_authorization_to_headers(endpoint.headers)

        return RequestData(
            query_params=query_params,
            body_params=body_params,
            file_params=file_params,
            headers=headers
        )

    async def _handle_file_upload(self, files: MediaDict) -> MediaDict | dict | None:
        """
        Uploads the files based on different upload strategies:
        (1) If the cloud handler is not set:
            - files are either converted to base64 or httpx based on the _attached_files_format setting.
            - else the files are attached as files in httpx.
        (2) If the cloud handler is set:
            - If the combined file size is below the limit, the files are attached using method (1)
            - If the combined file size is above the limit, the files are uploaded using the cloud handler.

        :param files: The files to be uploaded.
        :returns:
            - None: If no files were uploaded.
            - dict: If files were uploaded. The dict is formatted as { file_name: download_url }.
            - dict: If files are attached. The dict contains the files in a format that can be sent with httpx.
        """
        if not files or len(files) == 0:
            return None

        total_size = files.file_size('mb')
        if self.max_upload_file_size_mb and total_size > self.max_upload_file_size_mb:
            raise ValueError(f"File size exceeds limit of {self.max_upload_file_size_mb}MB")

        if not self.fast_cloud or not self.upload_to_cloud_threshold_mb or total_size < self.upload_to_cloud_threshold_mb:
            return files

        if isinstance(self.fast_cloud, BaseUploadAPI):
            return await self.fast_cloud.upload_async(files)
        return self.fast_cloud.upload(files)

    async def _prepare_files(self, files: MediaDict) -> tuple[dict, dict]:
        """Prepare files for request based on configuration."""
        if not files or len(files) == 0:
            return {}, {}

        # Get URL files (from cloud uploads)
        url_files = files.get_url_files()
        body_params = url_files.to_dict()

        # Process remaining files
        processable_files = files.get_processable_files(raise_exception=False, silent=True)

        if self._attached_files_format == 'base64':
            body_params.update(processable_files.to_base64())
            file_params = {}
        else:
            file_params = processable_files.to_httpx_send_able_tuple()

        return body_params, file_params

    def _build_request_url(self, endpoint: EndPoint, query_params: dict = None) -> str:
        """Build the complete request URL with query parameters."""
        base_url = f"{self.service_address.url}/{endpoint.endpoint_route}"
        if query_params:
            query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
            return f"{base_url}?{query_string}"
        return base_url

    async def _prepare_request_params(self, endpoint: EndPoint, *args, **kwargs) -> RequestData:
        """Prepare all request components."""
        # According to the endpoint definition, the request parameters are formatted.
        request_data = await self._format_request_params(endpoint, *args, **kwargs)

        # Process and prepare files
        media_files = MediaDict(files=request_data.file_params, download_files=False, read_system_files=True)

        processed_files = await self._handle_file_upload(media_files)
        if processed_files:
            body_files, file_params = await self._prepare_files(processed_files)
            request_data.file_params = file_params
            request_data.body_params.update(body_files)

        request_data.url = self._build_request_url(endpoint, request_data.query_params)
        return request_data

    async def _process_endpoint_request(self, endpoint: EndPoint, *args, **kwargs):
        """Process a complete endpoint request."""
        request_data = await self._prepare_request_params(endpoint, *args, **kwargs)

        return await self.httpx_client.post(
            url=request_data.url,
            params=request_data.query_params,
            data=request_data.body_params,
            files=request_data.file_params,
            headers=request_data.headers,
            timeout=endpoint.timeout
        )

    def request_endpoint(self, endpoint: EndPoint, callback: callable = None, *args, **kwargs) -> AsyncJob:
        """
        Submit an endpoint request as an async job.

        Args:
            endpoint: The endpoint definition
            callback: Optional callback function
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            AsyncJob object for tracking the request
        """
        req_coroutine = self._process_endpoint_request(endpoint, *args, **kwargs)
        return self.async_job_manager.submit(req_coroutine, callback=callback)

    def request_url(
            self,
            url: str,
            method: str = "GET",
            files: dict = None,
            callback: callable = None,
            delay: float = None,
            timeout: float = None,
    ) -> AsyncJob:
        """
        Submit a direct URL request as an async job.

        Args:
            url: Target URL
            method: HTTP method
            files: Optional files to upload
            callback: Optional callback function
            delay: Optional delay before execution
            timeout: Request timeout

        Returns:
            AsyncJob object for tracking the request
        """
        if not url.startswith(("http://", "https://")):
            url = f"{self.service_address.url}/{url.lstrip('/')}"

        headers = self._add_authorization_to_headers()

        method = method.upper()
        if method == "GET":
            req_coroutine = self.httpx_client.get(url=url, headers=headers, timeout=timeout)
        elif method == "POST":
            req_coroutine = self.httpx_client.post(url=url, files=files, headers=headers, timeout=timeout)
        elif method == "PUT":
            req_coroutine = self.httpx_client.put(url=url, files=files, headers=headers, timeout=timeout)
        elif method == "DELETE":
            req_coroutine = self.httpx_client.delete(url=url, headers=headers, timeout=timeout)
        else:
            req_coroutine = self.httpx_client.post(url=url, headers=headers, timeout=timeout)

        return self.async_job_manager.submit(req_coroutine, callback=callback, delay=delay)
