from pathlib import Path
from typing import Any, Dict, Optional, Union, TYPE_CHECKING
import os

from socaity_schemas.service_definitions import ServiceDefinition, ReplicateServiceAddress, RunpodServiceAddress, SocaityServiceAddress
from fastsdk.fastSDK import FastSDK

if TYPE_CHECKING:
    from fastsdk.service_interaction.api_seex import APISeex


class FastClient:
    """
    The runtime client for a service. Generated stubs inherit from this class, but it can also be
    used directly with any service source.

    A FastClient can be created from:
    - a registered service ID or name (this is what generated stubs do)
    - a service URL, an openapi.json file path, a spec dict or a ServiceDefinition
    - a Replicate model reference like "replicate:owner/name"

    If the source is not yet in the registry, it is loaded and registered automatically.

    Attributes:
        temporary: If True, the service is removed from the registry again when the client is
            deleted (or when used as a context manager, on exit). Defaults to False.
    """
    def __init__(
        self,
        service: Union[str, Path, Dict[str, Any], ServiceDefinition, None] = None,
        api_key: Optional[str] = None,
        temporary: bool = False,
        service_name_or_id: Optional[str] = None,
        **load_kwargs
    ):
        """
        Args:
            service: Service source. A registered service ID/name, a URL, a spec file path,
                a spec dict, a ServiceDefinition or a Replicate model reference.
            api_key: Optional API key for the service. If not provided, it is looked up in
                the environment variables (e.g. REPLICATE_API_KEY, RUNPOD_API_KEY, <SERVICE_ID>_API_KEY).
            temporary: If True, the service is removed from the registry when the client is deleted.
            service_name_or_id: Strict registry lookup by ID/name (used by generated stubs).
                Raises if the service is not registered.
            **load_kwargs: Additional arguments for service loading (see fastsdk.inspect_service).
        """
        self.fsdk = FastSDK()   # singleton: all clients share one registry and job manager
        self.temporary = temporary

        if service is None and service_name_or_id is None:
            raise ValueError("Provide a service source (URL, file, dict, ServiceDefinition) or a registered service ID/name.")

        if service_name_or_id is not None:
            # Strict lookup path used by generated stubs.
            self.service_definition = self.fsdk.service_registry.get_service(service_name_or_id)
            if not self.service_definition:
                raise ValueError(
                    f"Service '{service_name_or_id}' not found in the registry. "
                    f"Register it first with fastsdk.register_service(...) or regenerate the stub with fastsdk.generate_stub(...)."
                )
        else:
            self.service_definition = self._resolve_service(service, api_key, **load_kwargs)

        # try to get api key from global settings if not provided
        self.api_key = api_key or self._get_api_key()
        # Load the provider stack (client, file handler, parser) for this service.
        self.fsdk.provider_stacks.load(self.service_definition.id, self.api_key)

    def _resolve_service(self, service, api_key: Optional[str], **load_kwargs) -> ServiceDefinition:
        # A plain string might be a registered service ID/name - check the registry first.
        if isinstance(service, str):
            registered = self.fsdk.service_registry.get_service(service)
            if registered:
                return registered
        # Otherwise treat it as a spec source: load and register it.
        # Temporary clients always get their own registry entry (update_existing=False),
        # so removing it on cleanup never deletes a permanently registered service.
        service_def = self.fsdk.register_service(service, api_key=api_key, update_existing=not self.temporary, **load_kwargs)
        return service_def

    def _get_api_key(self):
        # for global services
        if isinstance(self.service_definition.service_address, SocaityServiceAddress):
            return os.getenv("SOCAITY_API_KEY", None)
        elif isinstance(self.service_definition.service_address, RunpodServiceAddress):
            return os.getenv("RUNPOD_API_KEY", None)
        elif isinstance(self.service_definition.service_address, ReplicateServiceAddress):
            return os.getenv("REPLICATE_API_KEY", None)
            
        # for locals try by service_id
        return os.getenv(self.service_definition.id.upper() + "_API_KEY", None)

    def submit_job(self, endpoint_id: str, **kwargs) -> 'APISeex':
        return self.fsdk.api_job_manager.submit_job(self.service_definition.id, endpoint_id, data=kwargs)

    def close(self):
        """Remove the service from the registry if this client registered it temporarily."""
        if self.temporary and getattr(self, 'service_definition', None) and hasattr(self, 'fsdk'):
            try:
                self.fsdk.service_registry.remove_service(self.service_definition.id)
            except Exception:
                # Ignore errors during cleanup (e.g., if FastSDK is already destroyed)
                pass
            self.temporary = False

    def __enter__(self) -> 'FastClient':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
