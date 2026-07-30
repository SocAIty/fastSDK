from typing import Any, Dict, Optional

from .api_client import APIClient, APIKeyError, RequestData
from socaity_schemas.contract import Endpoint, EndpointParameter, ServiceContract
from socaity_schemas.platform import PriceEstimate
from fastsdk.service_access import primary_deployment, service_contract
from fastsdk.requires import requires
import httpx
import json
from urllib.parse import urlparse

_FILE_FORMATS = frozenset({"file", "image", "video", "audio", "binary"})


def _normalize_endpoint_key(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower().replace("_", "-")


def _is_file_parameter(param: EndpointParameter) -> bool:
    definitions = param.definition
    if definitions is None:
        return False
    if not isinstance(definitions, list):
        definitions = [definitions]
    return any(d is not None and d.format in _FILE_FORMATS for d in definitions)


class APIClientSocaity(APIClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_method = "GET"

    def validate_api_key(self) -> bool:
        if self.address is None or "api.socaity.ai" not in self.address.base_url:
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

    def get_stream_url(self, response) -> Optional[str]:
        links = getattr(response, "links", None)
        return links.stream if links else None

    def _endpoint_for_url(self, url: str) -> Optional[Endpoint]:
        url_path = urlparse(url).path
        for ep in service_contract(self.service).endpoints:
            path = getattr(ep, "path", None) or ""
            if not path:
                continue
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
        content_type = getattr(endpoint, "request_body_content_type", None) if endpoint else None
        # Registered chat/LLM schemas must stay JSON even when a legacy contract
        # advertised form/urlencoded (flattened messages would be stringified).
        standard_schema = getattr(endpoint, "standard_schema", None) if endpoint else None
        body = {k: v for k, v in request_data.body_params.items() if v is not None}
        has_nested = any(isinstance(v, (dict, list)) for v in body.values())
        use_json = (
            content_type == "application/json"
            or (isinstance(standard_schema, str) and standard_schema.endswith("Request"))
            or (
                # Nested objects/arrays cannot round-trip through urlencoded forms
                # without being JSON-stringified; prefer a real JSON body instead.
                has_nested
                and content_type != "multipart/form-data"
            )
        )

        if use_json:
            kwargs["json"] = body
        else:
            form_data = {}
            for key, value in body.items():
                if isinstance(value, (dict, list)):
                    form_data[key] = json.dumps(value)
                else:
                    form_data[key] = value
            kwargs["data"] = form_data
            if request_data.file_params:
                kwargs["files"] = request_data.file_params

        request = self.client.build_request("POST", **kwargs)
        return await self.client.send(request, stream=True)

    @requires("socaity_cli", pip_name="socaity-cli", cli=False)
    def estimate(self, endpoint_path: str, **params) -> PriceEstimate:
        """Estimate price and runtime via the platform analytics API."""
        from socaity_cli import SocaityBackendClient

        deployment = primary_deployment(self.service)
        if not deployment.id:
            raise ValueError("Service has no deployment id; cannot estimate")

        contract = service_contract(self.service)
        endpoint = self._resolve_endpoint(endpoint_path, contract)
        input_data = self._estimate_input(endpoint, params)
        endpoint_id = self._platform_endpoint_id(endpoint.path)

        result = SocaityBackendClient().estimate(
            deployment_id=deployment.id,
            endpoint_id=endpoint_id,
            input_data=input_data,
        )
        if result is None:
            raise RuntimeError("estimate request failed")
        return result

    def _resolve_endpoint(self, endpoint_path: str, contract: ServiceContract) -> Endpoint:
        key = _normalize_endpoint_key(endpoint_path)
        for endpoint in contract.endpoints:
            if _normalize_endpoint_key(endpoint.path) == key:
                return endpoint
        available = ", ".join(ep.path for ep in contract.endpoints) or "(none)"
        raise ValueError(f"Unknown endpoint '{endpoint_path}'. Available endpoints: {available}")

    def _platform_endpoint_id(self, path: str) -> Optional[str]:
        key = _normalize_endpoint_key(path)
        for endpoint in self.service.endpoints or []:
            if endpoint.path and _normalize_endpoint_key(endpoint.path) == key:
                return endpoint.id
        return None

    @staticmethod
    def _estimate_input(endpoint: Endpoint, params: Dict[str, Any]) -> Dict[str, Any]:
        by_name = {param.name: param for param in endpoint.parameters}
        input_data: Dict[str, Any] = {}
        for name, param in by_name.items():
            if _is_file_parameter(param):
                continue
            value = params.get(name, param.default)
            if value is None or value == "":
                continue
            if hasattr(value, "to_json") or hasattr(value, "save"):
                continue
            input_data[name] = value
        for name, value in params.items():
            if name in input_data or name in by_name:
                continue
            if value is None or value == "" or hasattr(value, "to_json") or hasattr(value, "save"):
                continue
            input_data[name] = value
        return input_data
