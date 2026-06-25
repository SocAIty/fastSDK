from typing import Optional

from .api_client import APIClient, APIKeyError, RequestData
from apipod_registry.schemas.service_definitions import (
    EndpointDefinition,
    SocaityServiceAddress,
)
import httpx
import json
from urllib.parse import urlparse
# Must stay aligned with apipodgate endpoint_builder.parameter_utils (_is_llm_schema).
_LLM_BODY_SCHEMA_TITLES = frozenset({
    "ChatCompletionRequest",
    "CompletionRequest",
    "EmbeddingRequest",
})


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

    def get_poll_url(self, response) -> Optional[str]:
        links = getattr(response, "links", None)
        return links.status if links else None

    def get_cancel_url(self, response) -> Optional[str]:
        links = getattr(response, "links", None)
        return links.cancel if links else None

    @staticmethod
    def _endpoint_uses_json_body(endpoint: EndpointDefinition) -> bool:
        """APIPod gateway uses Body(JSON) for LLM schemas and RunPod-like /run endpoints."""
        # 1. LLM schemas
        for param in endpoint.parameters or []:
            if param.location != "body":
                continue
            schema = param.param_schema or {}
            if isinstance(schema, dict) and schema.get("title") in _LLM_BODY_SCHEMA_TITLES:
                return True

        # 2. RunPod-like endpoints (/run, /runsync) with an 'input' parameter
        path = (endpoint.path or "").strip("/")
        if path in ("run", "runsync"):
            for param in endpoint.parameters or []:
                if param.name == "input" and param.location == "body":
                    return True
        return False

    def _endpoint_for_url(self, url: str) -> Optional[EndpointDefinition]:
        url_path = urlparse(url).path
        for ep in self.service_def.endpoints or []:
            path = getattr(ep, "path", None) or ""
            if not path:
                continue
            # Match if URL path ends with endpoint path exactly
            if url_path.endswith(path):
                return ep
        return None

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        kwargs = {
            "url": request_data.url,
            "params": request_data.query_params,
            "headers": request_data.headers,
            "timeout": timeout_s,
        }
        
        endpoint = self._endpoint_for_url(request_data.url)
        use_json = False
        if not request_data.file_params:
            if endpoint is not None and self._endpoint_uses_json_body(endpoint):
                use_json = True

        if use_json:
            kwargs["json"] = request_data.body_params
        else:
            # SocAIty gateway expects form fields for non-LLM routes.
            # We manually JSON-serialize nested objects so they are valid JSON strings (double quotes).
            form_data = {}
            for k, v in request_data.body_params.items():
                if v is None:
                    continue
                if isinstance(v, (dict, list)):
                    form_data[k] = json.dumps(v)
                else:
                    form_data[k] = v
            kwargs["data"] = form_data
            if request_data.file_params:
                kwargs["files"] = request_data.file_params

        request = self.client.build_request("POST", **kwargs)
        return await self.client.send(request, stream=True)
