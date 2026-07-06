from typing import Optional

from .api_client import APIClient, APIKeyError, RequestData
from socaity_schemas.contract import Endpoint
from fastsdk.service_access import service_contract
import httpx
import json
from urllib.parse import urlparse


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

        if content_type == "application/json":
            kwargs["json"] = {k: v for k, v in request_data.body_params.items() if v is not None}
        else:
            # SocAIty gateway expects form fields for routes without a JSON requestBody.
            # We manually JSON-serialize nested objects so they are valid JSON strings (double quotes).
            form_data = {}
            for key, value in request_data.body_params.items():
                if value is None:
                    continue
                if isinstance(value, (dict, list)):
                    form_data[key] = json.dumps(value)
                else:
                    form_data[key] = value
            kwargs["data"] = form_data
            if request_data.file_params:
                kwargs["files"] = request_data.file_params

        request = self.client.build_request("POST", **kwargs)
        return await self.client.send(request, stream=True)
