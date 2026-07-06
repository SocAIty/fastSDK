from apipod_registry import Registry, create_service, materialize_contract, parse_address, determine_provider
from socaity_schemas.contract.address import service_url
from socaity_schemas.platform import AIModel, AIService, Provider

from fastsdk.service_access import primary_deployment, service_contract
from fastsdk.service_interaction import ApiJobManager
from fastsdk.service_interaction.provider_stack_registry import ProviderStackRegistry
from fastsdk.service_specification_loader.spec_loader import _load_from_runpod_serverless_server, _load_from_url_with_fallback, _load_from_file
from fastsdk.service_specification_loader.replicate_loader import parse_replicate_model_ref, load_replicate_service


from fastsdk.sdk_factory.sdk_factory import generate_stub as _generate_stub_file
from typing import Union, Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path
import uuid

if TYPE_CHECKING:
    from fastsdk.fastClient import FastClient
    from fastsdk.service_interaction import ApiJob
    from fastsdk.fastStub import FastStub


class FastSDK:
    """
    Internal facade that wires the service registry, spec loaders, the stub generator and the
    runtime job manager together. It is a singleton, so generated stubs and clients share one
    registry and one job manager per process.

    Most users should use the module-level functions instead:
    fastsdk.connect(), fastsdk.inspect_service(), fastsdk.generate_stub(), fastsdk.register_service()
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
        spec_source: Union[str, Path, Dict[str, Any], AIService],
        api_key: Optional[str] = None,
        provider: Optional[Provider] = None,
        service_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> AIService:
        """
        Load and parse a service into an AIService without adding it to the registry.

        Args:
            spec_source: What to inspect. Can be:
                - a URL ("http://localhost:8009", an openapi.json URL, a RunPod endpoint URL)
                - a Replicate model reference ("replicate:owner/name", "https://replicate.com/owner/name", "owner/name")
                - a file path to an openapi.json
                - an already loaded spec dict or an AIService
            api_key: Required for RunPod and Replicate sources, optional for others
            provider: Hosting provider override; inferred from the address when omitted
            service_id: Service id override; generated when omitted
            name: Service slug override; derived from the spec title when omitted

        Returns:
            AIService with one deployment carrying the parsed ServiceContract.
        """
        if isinstance(spec_source, AIService):
            return spec_source

        if isinstance(spec_source, dict):
            contract = materialize_contract(spec_source, provider=provider)
            return create_service(contract, provider=provider, service_id=service_id, name=name)

        if isinstance(spec_source, Path):
            spec = _load_from_file(spec_source)
            contract = materialize_contract(spec, provider=provider)
            return create_service(contract, provider=provider, service_id=service_id, name=name)

        if isinstance(spec_source, str) and "http" not in spec_source:
            # example black-forest-labs/flux-schnell:version
            ref = parse_replicate_model_ref(spec_source)
            if ref:
                return load_replicate_service(ref, api_key=api_key)
            # probably is a file path
            spec = _load_from_file(spec_source)
            contract = materialize_contract(spec, provider=provider)
            return create_service(contract, provider=provider, service_id=service_id, name=name)

        # Load from deployed service with address
        provider = provider or determine_provider(spec_source)
        address = parse_address(spec_source, provider=provider)
        if provider == "runpod":
            loaded_spec = _load_from_runpod_serverless_server(spec_source, api_key=api_key)
        else:
            loaded_spec = _load_from_url_with_fallback(service_url(address))

        contract = materialize_contract(loaded_spec, provider=provider)
        return create_service(contract, address=address, provider=provider, service_id=service_id, name=name)

    @staticmethod
    def load_openapi_spec_from_runpod(runpod_url: str, api_key: str, return_api_job: bool = False) -> Union[Dict[str, Any], 'ApiJob']:
        """Load the openapi spec dict from a RunPod serverless server.
        If return_api_job is True, return an ApiJob object instead of the spec dict.
        """
        return _load_from_runpod_serverless_server(runpod_url, api_key, return_api_job)

    # ---- Service Registration ----
    def register_service(
        self,
        spec_source: Union[str, Path, Dict[str, Any], AIService],
        service_id: Optional[str] = None,
        service_address: Optional[str] = None,
        service_name: Optional[str] = None,
        category: Union[str, List[str], None] = None,
        used_models: Union[str, AIModel, List[Union[str, AIModel]], None] = None,
        provider: Optional[Provider] = None,
        description: Optional[str] = None,
        api_key: Optional[str] = None,
        update_existing: bool = True
    ) -> AIService:
        """
        Load a service and add it to the registry. Idempotent: registering a service whose ID
        already exists replaces the previous entry (re-running the same script never fails).

        Args:
            spec_source: AIService or spec source (see inspect_service)
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service display name override
            category: Optional category id assignment (AIService.categories)
            used_models: Optional models used by the service; strings become AIModel(name=...)
            provider: Optional hosting provider override
            description: Optional description override
            api_key: Required for RunPod and Replicate sources, optional for others
            update_existing: If True and a service with the same name and spec format is already
                registered, that entry is updated (its ID is kept) instead of adding a duplicate.

        Returns:
            The registered AIService object
        """
        if isinstance(spec_source, AIService):
            service = spec_source
        else:
            service = self.inspect_service(spec_source, api_key, provider=provider)
            # Most specs (e.g. OpenAPI) don't embed a service ID, so every parse generates a fresh
            # one. Reuse the ID of an already registered service with the same name and spec format,
            # so re-runs update the existing entry and previously generated stubs stay valid.
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

        deployment = primary_deployment(service)
        deployment.service_id = service.id

        if provider:
            deployment.provider = provider

        # Forced local overwrite for runtime modification of the service address.
        # UseCase: You have a registered service and then change the address for it on runtime.
        if service_address:
            deployment.address = parse_address(service_address, provider=deployment.provider)

        if category:
            service.categories = [category] if isinstance(category, str) else category
        if used_models:
            models = used_models if isinstance(used_models, list) else [used_models]
            service.models = [m if isinstance(m, AIModel) else AIModel(name=m) for m in models]
        if description:
            service.description = description

        # Registry.add_service is an upsert: an existing service with the same ID is replaced.
        return self.service_registry.add_service(service)

    def update_service(self, service_id_or_name: str, **kwargs) -> Optional[AIService]:
        """
        Update attributes of a registered service.

        Args:
            service_id_or_name: Service ID, name or display name
            **kwargs: AIService attributes to update. "service_address" updates the
                primary deployment's address (string values go through the address parser).

        Returns:
            Updated AIService if found, None otherwise
        """
        service = self.service_registry.get_service(service_id_or_name)
        if not service:
            return None

        if "service_address" in kwargs:
            deployment = primary_deployment(service)
            deployment.address = parse_address(kwargs.pop("service_address"), provider=deployment.provider)

        for key, value in kwargs.items():
            setattr(service, key, value)

        return self.service_registry.add_service(service)

    def get_service(self, service_id_or_name: str) -> Optional[AIService]:
        """
        Get an already registered service by ID or name.

        Args:
            service_id_or_name: Service ID or display name

        Returns:
            AIService if found, None otherwise
        """
        return self.service_registry.get_service(service_id_or_name)

    # ---- Client / Stub Creation ----
    def generate_stub(
        self,
        source: Union[str, Path, Dict[str, Any], AIService],
        save_path: Optional[str] = None,
        class_name: Optional[str] = None,
        template: Optional[str] = None,
        **kwargs
    ) -> 'FastStub':
        """
        Generate a Python client stub file (.py) for a service and register the service in the registry.

        Args:
            source: Service source (URL, file path, spec dict, AIService, or a registered service ID/name)
            save_path: Path (file or directory) to save the generated file. Defaults to the current directory.
            class_name: Name for the generated class. Defaults to the service name.
            template: Optional custom Jinja2 template path
            **kwargs: Additional arguments for service loading (e.g. api_key, service_name)

        Returns:
            FastStub with .path, .class_name, .service and .client()
        """
        # Get or load the service
        service = source
        if isinstance(source, str):
            service = self.get_service(source)
            if not isinstance(service, AIService):
                service = self.register_service(source, **kwargs)
        else:
            service = self.register_service(source, **kwargs)

        if not isinstance(service, AIService):
            raise ValueError("Invalid service source")

        return _generate_stub_file(service, save_path, class_name, template)

    def connect(
        self,
        source: Union[str, Path, Dict[str, Any], AIService],
        api_key: Optional[str] = None,
        **kwargs
    ) -> 'FastClient':
        """
        Connect to a service and return a ready-to-use client - no code generation involved.
        The service is registered temporarily and removed again when the client is deleted.

        Args:
            source: Service source (URL, file path, spec dict, AIService or Replicate model ref)
            api_key: Optional API key for the service
            **kwargs: Additional arguments for service loading

        Returns:
            FastClient instance. Call endpoints via client.endpoint_name(...) after stub generation,
            or generically via client.submit_job("/endpoint", **params).
        """
        from fastsdk.fastClient import FastClient
        return FastClient(source, api_key=api_key, temporary=True, **kwargs)
