from typing import Any, Optional

import httpx
from fastsdk.service_interaction.request.api_client import APIClient, APIKeyError, RequestData
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk.service_interaction.response.response_schemas import SocaityJobResponse
from socaity_schemas.contract import Endpoint
from socaity_schemas.contract.address import service_url

# Keys that are transport/worker metadata, never part of a schema request body.
_RESERVED_INPUT_KEYS = frozenset({"path", "task_id"})


class APIClientRunpod(APIClient):
    def validate_api_key(self) -> bool:
        if self.address is None or "api.runpod.ai" not in self.address.base_url:  # pass for non officially hosted or localhost services
            return True
        if self.api_key is None:
            raise APIKeyError("API key is required for Runpod API.", "runpod", "https://www.runpod.io/")
        if not self.api_key.startswith("rpa_"):
            raise APIKeyError("Invalid API key. It should look like 'rpa_...'. ", "runpod", "https://www.runpod.io/")
        return True

    def _build_request_url(self, endpoint: Endpoint, query_params: dict | None = None) -> str:
        # Overwrites the default implementation, because query parameters are not added to the url but to the body
        url = service_url(self.address).strip("/")  # don't use strip("/run") it will remove the letters / r u and n.
        if url.endswith("/run"):
            url = url[:-4]  # Remove "/run" suffix
        return f"{url}/run"

    def get_poll_url(self, response) -> Optional[str]:
        return f"status/{response.id}"

    def get_cancel_url(self, response) -> Optional[str]:
        return f"cancel/{response.id}"

    def get_result(self, response) -> Any:
        return getattr(response, "output", None)

    def format_request_params(self, endpoint: Endpoint, data: dict) -> RequestData:
        """Prepare request parameters for Runpod API.

        Shared ``APIClient`` spreads a sole JSON object body onto the wire root
        for HTTP. RunPod ``input`` is function kwargs, so re-nest that object
        under the schema param name (usually ``request``) and keep ``path``.

        Also accepts flat schema fields when the catalog still lists one object
        body param (callers pass ``messages=...`` instead of ``request={...}``),
        and nests flattened ``standard_schema`` contracts under ``request``.
        Plain multi-arg endpoints are left untouched.
        """
        data = self._coalesce_flat_schema_input(endpoint, data)
        request_data = super().format_request_params(endpoint, data)
        request_data.body_params = self._renest_schema_body_for_runpod(
            endpoint, request_data.body_params
        )

        # adding path to the body for runpod apipod services
        if endpoint.path:
            request_data.body_params["path"] = endpoint.path

        return request_data

    @classmethod
    def _sole_json_object_body_param(cls, endpoint: Endpoint):
        body_defs = [p for p in (endpoint.parameters or []) if p.location == "body"]
        if len(body_defs) == 1 and cls._is_json_object_request_body(body_defs[0]):
            return body_defs[0]
        return None

    @classmethod
    def _coalesce_flat_schema_input(cls, endpoint: Endpoint, data: dict) -> dict:
        """Wrap flat schema fields into the sole body param before HTTP-style formatting.

        Example: catalog has ``request: ChatCompletionRequest``, caller passes
        ``{messages: [...]}`` → ``{request: {messages: [...]}}``.
        """
        if not isinstance(data, dict) or not data:
            return data

        body_param = cls._sole_json_object_body_param(endpoint)
        if body_param is None:
            return data

        name = body_param.name
        if name in data:
            return data

        schema = getattr(body_param, "param_schema", None) or {}
        schema_props = set(schema.get("properties") or {})
        flat = {
            k: v for k, v in data.items()
            if k not in _RESERVED_INPUT_KEYS and k != name
        }
        if not flat:
            return data
        if schema_props and not (set(flat) & schema_props):
            return data

        keep = {k: v for k, v in data.items() if k in _RESERVED_INPUT_KEYS}
        return {name: flat, **keep}

    @classmethod
    def _renest_schema_body_for_runpod(cls, endpoint: Endpoint, body_params: dict) -> dict:
        """Ensure RunPod kwargs include the schema object param when applicable."""
        if not body_params:
            return body_params

        body_param = cls._sole_json_object_body_param(endpoint)
        if body_param is not None:
            return cls._renest_under(body_param.name, body_params)

        # Legacy flattened catalog for a standardized LLM schema: nest under request.
        if not getattr(endpoint, "standard_schema", None):
            return body_params
        if "request" in body_params:
            return body_params
        return cls._renest_under("request", body_params)

    @classmethod
    def _renest_under(cls, name: str, body_params: dict) -> dict:
        if name in body_params:
            return body_params
        nested = {k: v for k, v in body_params.items() if k not in _RESERVED_INPUT_KEYS}
        keep = {k: v for k, v in body_params.items() if k in _RESERVED_INPUT_KEYS}
        if not nested:
            return body_params
        return {name: nested, **keep}

    # Back-compat alias used by older tests / callers.
    @classmethod
    def _renest_sole_json_object_body(cls, endpoint: Endpoint, body_params: dict) -> dict:
        return cls._renest_schema_body_for_runpod(endpoint, body_params)

    async def send_request(self, request_data: RequestData, timeout_s: float = 60) -> httpx.Response:
        """
        Send the prepared request to the API.
        """
        # runpod wants all parameters in the body. If it is a an apipod service the "path" is in the body.
        # so we need to check if the service is a apipod service and if so, we need to add the path to the body.
        
        all_params = request_data.body_params
        all_params.update(request_data.query_params)
        all_params.update(request_data.file_params)

        return await self.client.post(
            url=request_data.url,
            json={"input": all_params},
            headers=request_data.headers,
            timeout=timeout_s
        )


class APIClientRunpodApipod(APIClientRunpod):
    """Runpod transport for initial request, Socaity-style polling once
    the nested APIPod payload appears in the output.

    The parser returns ``SocaityJobResponse`` when the nested payload is
    found, and ``RunpodJobResponse`` while still queued.  This client
    adapts its behaviour based on which type it receives.
    """

    def get_poll_url(self, response) -> Optional[str]:
        if isinstance(response, SocaityJobResponse):
            return response.links.status if response.links else None
        return super().get_poll_url(response)

    def get_cancel_url(self, response) -> Optional[str]:
        if isinstance(response, SocaityJobResponse):
            return response.links.cancel if response.links else None
        return super().get_cancel_url(response)

    def get_result(self, response) -> Any:
        if isinstance(response, SocaityJobResponse):
            return response.result
        return super().get_result(response)

    def get_status(self, response) -> APIJobStatus:
        if isinstance(response, SocaityJobResponse):
            return APIJobStatus.from_str(response.status)
        return super().get_status(response)

    async def poll_status(self, response) -> httpx.Response:
        url = self.get_poll_url(response)
        if not url:
            raise ValueError("No polling URL available")
        method = "GET" if isinstance(response, SocaityJobResponse) else self.poll_method
        return await self.request_url(url=url, method=method)
