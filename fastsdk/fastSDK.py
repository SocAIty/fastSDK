import uuid

from apipod_registry import Registry, create_service, materialize_contract, parse_address, determine_provider
from socaity_schemas.public.spec.address import service_url
from socaity_schemas.platform.catalog.model import AIModel
from socaity_schemas.platform.catalog.service import Service
from socaity_schemas.platform.catalog.hosting import Provider

from fastsdk.service_access import details_provider, primary_details, service_contract, set_reachability
from fastsdk.service_interaction import ApiJobManager
from fastsdk.service_interaction.provider_stack_registry import ProviderStackRegistry
from fastsdk.service_specification_loader.spec_loader import _load_from_runpod_serverless_server, _load_from_file
from fastsdk.service_specification_loader.openapi_discovery import load_openapi_from_url
from fastsdk.service_specification_loader.replicate_loader import parse_replicate_model_ref, load_replicate_service

from typing import Union, Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from fastsdk.fastClient import FastClient
    from fastsdk.service_interaction import ApiJob


class FastSDK:
    """
    Internal facade that wires the service registry, spec loaders, and the
    runtime job manager together. It is a singleton, so clients share one
    registry and one job manager per process.

    Most users should use the module-level functions instead:
    fastsdk.connect(), fastsdk.inspect_service(), fastsdk.register_service()
    """
    _instance: 'FastSDK' = None

    def __new__(cls) -> 'FastSDK':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._service_registry = None
            self._provider_stacks = None
            self._api_job_manager = None
            # Default verbosity level. Set directly after first init to change it;
            # or before api_job_manager is used the first time.
            self._progress_verbosity = 2
            self._initialized = True

    @property
    def service_registry(self) -> Registry:
        if self._service_registry is None:
            self._service_registry = Registry()
        return self._service_registry

    @service_registry.setter
    def service_registry(self, value: Registry):
        self._service_registry = value
        if self._provider_stacks:
            self._provider_stacks.registry = value
        if self._api_job_manager:
            self._api_job_manager.service_registry = value

    @property
    def provider_stacks(self) -> ProviderStackRegistry:
        if self._provider_stacks is None:
            self._provider_stacks = ProviderStackRegistry(self.service_registry)
        return self._provider_stacks

    @property
    def api_job_manager(self) -> ApiJobManager:
        if self._api_job_manager is None:
            self._api_job_manager = ApiJobManager(
                self.service_registry,
                self.provider_stacks,
                progress_verbosity=self._progress_verbosity,
            )
        return self._api_job_manager

    @api_job_manager.setter
    def api_job_manager(self, value: ApiJobManager):
        self._api_job_manager = value

    # ---- Service Inspection (pure, no registry side effects) ----
    @staticmethod
    def inspect_service(
        spec_source: Union[str, Path, Dict[str, Any], Service],
        api_key: Optional[str] = None,
        provider: Optional[Provider] = None,
        service_id: Optional[str] = None,
        slug: Optional[str] = None,
    ) -> Service:
        """
        Load and parse a service into an Service without adding it to the registry.

        Args:
            spec_source: What to inspect. Can be:
                - a URL ("http://localhost:8009", an openapi.json URL, a RunPod endpoint URL)
                - a Replicate model reference ("replicate:owner/name", "https://replicate.com/owner/name", "owner/name")
                - a file path to an openapi.json
                - an already loaded spec dict or an Service
            api_key: Required for RunPod and Replicate sources, optional for others
            provider: Hosting provider override; inferred from the address when omitted
            service_id: Service id override; generated when omitted
            slug: Service slug override; derived from the spec title when omitted

        Returns:
            Service with one details binding carrying the parsed ServiceContract.
        """
        if isinstance(spec_source, Service):
            return spec_source

        if isinstance(spec_source, dict):
            contract = materialize_contract(spec_source, provider=provider)
            return create_service(contract, provider=provider, service_id=service_id, slug=slug)

        if isinstance(spec_source, Path):
            spec = _load_from_file(spec_source)
            contract = materialize_contract(spec, provider=provider)
            return create_service(contract, provider=provider, service_id=service_id, slug=slug)

        if isinstance(spec_source, str) and "http" not in spec_source:
            # example black-forest-labs/flux-schnell:version
            ref = parse_replicate_model_ref(spec_source)
            if ref:
                return load_replicate_service(ref, api_key=api_key)
            # probably is a file path
            spec = _load_from_file(spec_source)
            contract = materialize_contract(spec, provider=provider)
            return create_service(contract, provider=provider, service_id=service_id, slug=slug)

        # Load from deployed service with address
        provider = provider or determine_provider(spec_source)
        address = parse_address(spec_source, provider=provider)
        spec_url = None
        if provider == "runpod":
            loaded_spec = _load_from_runpod_serverless_server(spec_source, api_key=api_key)
        else:
            spec_url, loaded_spec = load_openapi_from_url(service_url(address), timeout=8)

        contract = materialize_contract(loaded_spec, provider=provider)
        service = create_service(contract, address=address, provider=provider, service_id=service_id, slug=slug)
        service.details[0].spec_url = spec_url
        return service

    @staticmethod
    def load_openapi_spec_from_runpod(runpod_url: str, api_key: str, return_api_job: bool = False) -> Union[Dict[str, Any], 'ApiJob']:
        """Load the openapi spec dict from a RunPod serverless server.
        If return_api_job is True, return an ApiJob object instead of the spec dict.
        """
        return _load_from_runpod_serverless_server(runpod_url, api_key, return_api_job)

    # ---- Service Registration ----
    def register_service(
        self,
        spec_source: Union[str, Path, Dict[str, Any], Service],
        service_id: Optional[str] = None,
        service_address: Optional[str] = None,
        service_name: Optional[str] = None,
        category: Union[str, List[str], None] = None,
        used_models: Union[str, AIModel, List[Union[str, AIModel]], None] = None,
        provider: Optional[Provider] = None,
        description: Optional[str] = None,
        api_key: Optional[str] = None,
        update_existing: bool = True
    ) -> Service:
        """
        Load a service and add it to the registry. Idempotent: registering a service whose ID
        already exists replaces the previous entry (re-running the same script never fails).

        Args:
            spec_source: Service or spec source (see inspect_service)
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service display name override
            category: Optional category id assignment (Service.categories)
            used_models: Optional models used by the service; strings become AIModel(name=...)
            provider: Optional hosting provider override
            description: Optional description override
            api_key: Required for RunPod and Replicate sources, optional for others
            update_existing: If True and a service with the same name and spec format is already
                registered, that entry is updated (its ID is kept) instead of adding a duplicate.

        Returns:
            The registered Service object
        """
        if isinstance(spec_source, Service):
            service = spec_source
        else:
            service = self.inspect_service(spec_source, api_key, provider=provider)
            # Most specs (e.g. OpenAPI) don't embed a service ID, so every parse generates a fresh
            # one. Reuse the ID of an already registered service with the same name and spec format,
            # so re-runs update the existing entry.
            if update_existing and service_id is None and service.display_name:
                existing = self.service_registry.get_service(service.display_name)
                if existing is not None and service_contract(existing).specification == service_contract(service).specification:
                    service.id = existing.id

        # Apply overrides
        if service_id:
            service.id = service_id
        elif not service.id:
            service.id = "gen-" + str(uuid.uuid4())

        if service_name:
            service.display_name = service_name
        elif not service.display_name:
            service.display_name = "unnamed_service_" + service.id

        details = primary_details(service)
        details.service_id = service.id

        if provider:
            set_reachability(details, provider=provider)

        # Forced local overwrite for runtime modification of the service address.
        # UseCase: You have a registered service and then change the address for it on runtime.
        if service_address:
            set_reachability(
                details,
                address=parse_address(service_address, provider=details_provider(details)),
            )

        if category:
            service.categories = [category] if isinstance(category, str) else category
        if used_models:
            models = used_models if isinstance(used_models, list) else [used_models]
            service.models = [m if isinstance(m, AIModel) else AIModel(name=m) for m in models]
        if description:
            service.description = description

        # Replace, not merge: Registry.add_service merges bindings by details id (gate hydration),
        # which would keep a stale cached binding in front of the fresh one.
        self.service_registry.remove_service(service.id, persist=False)
        return self.service_registry.add_service(service)

    def get_service(self, service_id_or_name: str) -> Optional[Service]:
        """
        Get an already registered service by ID or name.

        Args:
            service_id_or_name: Service ID or display name

        Returns:
            Service if found, None otherwise
        """
        return self.service_registry.get_service(service_id_or_name)

    def connect(
        self,
        source: Union[str, Path, Dict[str, Any], Service],
        api_key: Optional[str] = None,
        **kwargs
    ) -> 'FastClient':
        """
        Connect to a service and return a ready-to-use client.
        The service is registered temporarily and removed again when the client is deleted.

        Args:
            source: Service source (URL, file path, spec dict, Service or Replicate model ref)
            api_key: Optional API key for the service
            **kwargs: Additional arguments for service loading

        Returns:
            FastClient. Call endpoints via client.submit_job("/endpoint", **params).
        """
        from fastsdk.fastClient import FastClient
        return FastClient(source, api_key=api_key, temporary=True, **kwargs)
