from pathlib import Path
from typing import Any, Dict, Optional, Union, TYPE_CHECKING
import os

from socaity_schemas.platform import AIService, PriceEstimate

from fastsdk.fastSDK import FastSDK
from fastsdk.service_access import service_provider

if TYPE_CHECKING:
    from fastsdk.service_interaction.api_seex import APISeex


_PROVIDER_API_KEY_ENV = {
    "socaity": "SOCAITY_API_KEY",
    "runpod": "RUNPOD_API_KEY",
    "replicate": "REPLICATE_API_KEY",
}


class FastClient:
    """
    The runtime client for a service. Generated stubs inherit from this class, but it can also be
    used directly with any service source.

    A FastClient can be created from:
    - a registered service ID or name (this is what generated stubs do)
    - a service URL, an openapi.json file path, a spec dict or an AIService
    - a Replicate model reference like "replicate:owner/name"

    If the source is not yet in the registry, it is loaded and registered automatically.

    Attributes:
        temporary: If True, the service is removed from the registry again when the client is
            deleted (or when used as a context manager, on exit). Defaults to False.
    """
    def __init__(
        self,
        service: Union[str, Path, Dict[str, Any], AIService, None] = None,
        api_key: Optional[str] = None,
        temporary: bool = False,
        service_name_or_id: Optional[str] = None,
        materialize_media: bool = True,
        **load_kwargs
    ):
        """
        Args:
            service: Service source. A registered service ID/name, a URL, a spec file path,
                a spec dict, an AIService or a Replicate model reference.
            api_key: Optional API key for the service. If not provided, it is looked up in
                the environment variables (e.g. REPLICATE_API_KEY, RUNPOD_API_KEY, <SERVICE_ID>_API_KEY).
            temporary: If True, the service is removed from the registry when the client is deleted.
            service_name_or_id: Strict registry lookup by ID/name (used by generated stubs).
                Raises if the service is not registered.
            materialize_media: If False, media results stay URL references instead of being
                downloaded. Agent hosts (MCP) use this to avoid pulling bytes they only forward.
            **load_kwargs: Additional arguments for service loading (see fastsdk.inspect_service).
        """
        self.fsdk = FastSDK()   # singleton: all clients share one registry and job manager
        self.temporary = temporary
        self.materialize_media = materialize_media

        if service is None and service_name_or_id is None:
            raise ValueError("Provide a service source (URL, file, dict, AIService) or a registered service ID/name.")

        if service_name_or_id is not None:
            self.service = self.fsdk.service_registry.get_service(service_name_or_id)
            if not self.service:
                raise ValueError(
                    f"Service '{service_name_or_id}' not found in the registry. "
                    f"Register it first with fastsdk.register_service(...) or regenerate the stub with fastsdk.generate_stub(...)."
                )
        else:
            self.service = self._resolve_service(service, api_key, **load_kwargs)

        # try to get api key from global settings if not provided
        self.api_key = api_key or self._get_api_key()
        self.fsdk.provider_stacks.load(self.service.id, self.api_key)

    def _resolve_service(self, service, api_key: Optional[str], **load_kwargs) -> AIService:
        # A plain string might be a registered service ID/name - check the registry first.
        if isinstance(service, str):
            registered = self.fsdk.service_registry.get_service(service)
            if registered:
                return registered
        # Otherwise treat it as a spec source: load and register it.
        # Temporary clients always get their own registry entry (update_existing=False),
        # so removing it on cleanup never deletes a permanently registered service.
        return self.fsdk.register_service(service, api_key=api_key, update_existing=not self.temporary, **load_kwargs)

    def _get_api_key(self):
        env_var = _PROVIDER_API_KEY_ENV.get(service_provider(self.service))
        if env_var:
            return os.getenv(env_var, None)
        return os.getenv(self.service.id.upper() + "_API_KEY", None)

    def submit_job(self, endpoint_id: str, **kwargs) -> 'APISeex':
        return self.fsdk.api_job_manager.submit_job(
            self.service.id,
            endpoint_id,
            data=kwargs,
            api_key=self.api_key,
            materialize_media=self.materialize_media,
        )

    def estimate(self, endpoint_path: str, **params) -> PriceEstimate:
        """Estimate price and runtime. Implemented by the Socaity provider API client.

        Requires ``socaity-cli`` when the provider is Socaity (signaled via ``@requires``).
        """
        stack = self.fsdk.provider_stacks.require(self.service.id, self.api_key)
        estimate_fn = getattr(stack.api_client, "estimate", None)
        if estimate_fn is None:
            raise NotImplementedError(
                "estimate() is only available for Socaity-hosted services "
                f"(provider client: {type(stack.api_client).__name__})"
            )
        return estimate_fn(endpoint_path, **params)

    def close(self):
        """Remove the service from the registry if this client registered it temporarily."""
        if self.temporary and getattr(self, 'service', None) and hasattr(self, 'fsdk'):
            try:
                self.fsdk.service_registry.remove_service(self.service.id)
            except Exception:
                pass
            self.temporary = False

    def __enter__(self) -> 'FastClient':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
