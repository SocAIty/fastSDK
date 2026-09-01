from typing import Dict, Any, Optional, Union
import json
import httpx
from urllib.parse import urlencode

from socaity_schemas.contract import Endpoint
from socaity_schemas.contract.address import endpoint_url, resolve_url
from socaity_schemas.platform import AIService
from fastsdk.service_access import service_address
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from media_toolkit import MediaFile, MediaDict, MediaList


class APIKeyError(Exception):
    """Custom exception for API key validation errors."""
    def __init__(self, message: str, service_name: str, signup_url: str):
        message = f"{message}\nPlease create an account at {signup_url} and get an API key. Set the API key using environment variable {service_name.upper()}_API_KEY."
        super().__init__(message)


class RequestData:
    def __init__(
        self,
        query_params: dict = {},
        body_params: dict = {},
        file_params: Union[dict, Any, None] = {},
        headers: dict = {},
        url: str = "",
        body_content_type: Optional[str] = None,
    ):
        self.query_params = query_params or {}
        self.body_params = body_params or {}
        self.file_params = file_params or {}
        self.headers = headers or {}
        self.url = url
        self.body_content_type = body_content_type


class APIClient:
    """Handles all HTTP interactions with APIs.

    Subclasses override the ``get_*`` accessors to teach the base
    ``poll_status`` / ``cancel_job`` methods how to extract URLs and
    status from their provider-specific response models.
    """

    _FILE_FORMATS = frozenset({"file", "image", "video", "audio"})
    _JSON_BODY_CONTENT_TYPE = "application/json"
    _MULTIPART_BODY_CONTENT_TYPE = "multipart/form-data"
    _FORM_BODY_CONTENT_TYPE = "application/x-www-form-urlencoded"
    _BODY_CONTENT_TYPES = (
        _JSON_BODY_CONTENT_TYPE,
        _MULTIPART_BODY_CONTENT_TYPE,
        _FORM_BODY_CONTENT_TYPE,
    )

    def __init__(self, service: AIService, api_key: str = None):
        self.__client = None
        self.service = service
        self.address = service_address(service)
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

    def get_stream_url(self, response) -> Optional[str]:
        """URL of a live output stream for an in-progress job, if the provider exposes one."""
        return None

    def get_result(self, response) -> Any:
        from fastsdk.service_interaction.response.response_parser import (
            normalize_provider_result,
        )
        return normalize_provider_result(getattr(response, "result", None))

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

    def _build_request_url(self, endpoint: Endpoint, query_params: Dict = None) -> str:
        if not self.address:
            return None
        base_url = endpoint_url(self.address, endpoint.path)
        if query_params:
            query_string = urlencode(query_params, doseq=True)
            return f"{base_url}?{query_string}"
        return base_url

    @classmethod
    def _param_has_file_format(cls, param) -> bool:
        definitions = getattr(param, "definition", None)
        if definitions is None:
            return False
        defs = definitions if isinstance(definitions, list) else [definitions]
        return any(getattr(d, "format", None) in cls._FILE_FORMATS for d in defs)

    @classmethod
    def _param_is_file_model(cls, param) -> bool:
        """True when the param expects an APIPod FileModel JSON payload, not a raw upload."""
        definitions = getattr(param, "definition", None)
        if definitions is None:
            return False
        defs = definitions if isinstance(definitions, list) else [definitions]
        formats = {getattr(d, "format", None) for d in defs}
        raw_formats = {"binary", "image", "video", "audio"}
        return "file" in formats and not formats.intersection(raw_formats)

    @classmethod
    def _schema_accepts_binary_upload(cls, param) -> bool:
        """True when the OpenAPI schema allows a raw octet-stream upload."""
        schema = getattr(param, "param_schema", None) or {}
        if not isinstance(schema, dict):
            return False
        options = schema.get("anyOf") or schema.get("oneOf") or []
        for option in options:
            if not isinstance(option, dict):
                continue
            if option.get("type") == "string" and option.get("contentMediaType") == "application/octet-stream":
                return True
        return False

    @classmethod
    def _param_accepts_raw_upload(cls, param) -> bool:
        definitions = getattr(param, "definition", None)
        if definitions is None:
            return cls._schema_accepts_binary_upload(param)
        defs = definitions if isinstance(definitions, list) else [definitions]
        if any(getattr(d, "format", None) in {"binary", "image", "video", "audio"} for d in defs):
            return True
        return cls._schema_accepts_binary_upload(param)

    def partition_media_for_multipart(self, endpoint: Endpoint, files: MediaDict) -> tuple[dict, MediaDict]:
        """Split loaded media into FileModel JSON body fields and raw multipart uploads."""
        file_model_body = {}
        raw_files = {}
        for param in endpoint.parameters:
            if param.name not in files:
                continue
            value = files[param.name]
            if self._param_is_file_model(param) and not self._param_accepts_raw_upload(param):
                if isinstance(value, list):
                    file_model_body[param.name] = [
                        item.to_json() if hasattr(item, "to_json") else item for item in value
                    ]
                else:
                    file_model_body[param.name] = value.to_json() if hasattr(value, "to_json") else value
            else:
                raw_files[param.name] = value
        return file_model_body, MediaDict(files=raw_files) if raw_files else MediaDict({})

    @staticmethod
    def _encode_form_fields(body_params: dict) -> dict:
        """Encode multipart/form fields. Nested models become JSON strings."""
        encoded = {}
        for key, value in body_params.items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                encoded[key] = json.dumps(value)
            else:
                encoded[key] = value
        return encoded

    @staticmethod
    def _is_file_model_dict(value: Any) -> bool:
        return isinstance(value, dict) and {"file_name", "content_type", "content"}.issubset(value.keys())

    @classmethod
    def _serialize_json_body_file_value(cls, value: Any) -> Any:
        """Convert a file field to APIPod FileModel JSON for application/json bodies."""
        if isinstance(value, MediaFile):
            return value.to_json()
        if isinstance(value, (list, tuple, MediaList)):
            # List-typed schema fields (e.g. images: List[ImageFileModel]) arrive
            # as a MediaList after file loading; serialize item by item.
            return [cls._serialize_json_body_file_value(item) for item in value]
        if cls._is_file_model_dict(value):
            return value
        return value

    @classmethod
    def _is_scalar_value(cls, value: Any) -> bool:
        return isinstance(value, (str, int, float, bool)) or value is None

    @classmethod
    def _uses_json_request_body(cls, endpoint: Endpoint) -> bool:
        return getattr(endpoint, "request_body_content_type", None) == cls._JSON_BODY_CONTENT_TYPE

    @staticmethod
    def _is_json_object_request_body(param) -> bool:
        schema = getattr(param, "param_schema", None) or {}
        if not isinstance(schema, dict):
            return False
        if schema.get("type") == "object" and schema.get("properties"):
            return True
        return bool(schema.get("properties"))

    def format_request_params(self, endpoint: Endpoint, data: dict) -> RequestData:
        """Prepare all request parameters for the endpoint."""
        body_content_type = getattr(endpoint, "request_body_content_type", None)

        if not data:
            rq = RequestData(body_content_type=body_content_type)
            rq.headers = self._add_authorization_to_headers()
            rq.url = self._build_request_url(endpoint, rq.query_params)
            return rq

        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        rq = RequestData(body_content_type=body_content_type)
        embed_files_in_json_body = self._uses_json_request_body(endpoint)
        body_params = [p for p in endpoint.parameters if p.location == "body"]
        # Sole JSON object body (e.g. ChatCompletionRequest as ``request``):
        # spread model fields onto the wire root. Callers still pass request={...}.
        single_json_object_body = (
            embed_files_in_json_body
            and len(body_params) == 1
            and self._is_json_object_request_body(body_params[0])
        )

        for param in endpoint.parameters:
            param_value = data.get(param.name, param.default)
            if param_value is None and param.required:
                raise ValueError(f"Required parameter '{param.name}' is missing")

            has_file_format = self._param_has_file_format(param)
            is_array_param = False

            schema = getattr(param, "param_schema", None) or {}
            if isinstance(schema, dict) and schema.get("type") == "array":
                is_array_param = True

            is_file_model = self._param_is_file_model(param)
            accepts_raw_upload = self._param_accepts_raw_upload(param)
            is_media_file = isinstance(param_value, MediaFile)
            is_file_upload = is_media_file or accepts_raw_upload or (
                has_file_format and param_value is not None and not (
                    embed_files_in_json_body and self._is_file_model_dict(param_value)
                )
            ) or (is_file_model and param_value is not None)

            if is_array_param and not isinstance(param_value, list):
                param_value = [param_value]

            if is_file_upload and embed_files_in_json_body:
                if isinstance(param_value, MediaFile) or self._is_file_model_dict(param_value):
                    rq.body_params[param.name] = self._serialize_json_body_file_value(param_value)
                else:
                    rq.file_params[param.name] = param_value
            elif is_file_upload:
                rq.file_params[param.name] = param_value
            elif param.location == "query":
                rq.query_params[param.name] = param_value
            elif param.location == "body":
                if param_value is not None:
                    if single_json_object_body and param.name == body_params[0].name:
                        if isinstance(param_value, dict):
                            rq.body_params.update(param_value)
                        elif hasattr(param_value, "model_dump"):
                            rq.body_params.update(
                                param_value.model_dump(mode="json", exclude_none=True)
                            )
                        else:
                            rq.body_params[param.name] = param_value
                    else:
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

        if (
            request_data.body_content_type == self._JSON_BODY_CONTENT_TYPE
            and request_data.file_params
        ):
            for name, value in dict(request_data.file_params).items():
                request_data.body_params[name] = self._serialize_json_body_file_value(value)
            request_data.file_params = {}

        if request_data.file_params:
            kwargs["data"] = self._encode_form_fields(request_data.body_params)
            kwargs["files"] = request_data.file_params
        elif request_data.body_content_type == self._FORM_BODY_CONTENT_TYPE:
            kwargs["data"] = self._encode_form_fields(request_data.body_params)
        else:
            kwargs["json"] = {k: v for k, v in request_data.body_params.items() if v is not None}

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
        if not self.address:
            raise ValueError("Service address is required to request a relative URL")

        url = resolve_url(self.address, url)
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

    async def cancel_job(self, response, action: Optional[str] = None) -> httpx.Response:
        """Cancel a job. ``action`` (``cancel`` | ``interrupt``) is a Socaity/APIPod
        query parameter; ``interrupt`` keeps a resumable checkpoint on agent jobs."""
        url = self.get_cancel_url(response)
        if not url:
            raise ValueError("No cancel URL available for this response")
        params = {"action": action} if action else None
        return await self.request_url(url=url, method=self.cancel_method, params=params)

    async def open_stream(self, response) -> httpx.Response:
        """Open the provider's live output stream for an in-progress job.

        Returns an open (streaming) httpx response. The caller owns closing it.
        """
        url = self.get_stream_url(response)
        if not url:
            raise ValueError("No stream URL available for this response")
        return await self.request_url(url=url, method="GET")
