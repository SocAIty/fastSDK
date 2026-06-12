from apipod_registry import Registry
from apipod_registry.definitions.service_definitions import ServiceDefinition, ModelDefinition
from apipod_registry.parsers import parse_service_definition
from apipod_registry.parsers.service_adress_parser import create_service_address

from fastsdk.fastStub import FastStub
from fastsdk.service_interaction import ApiJobManager
from fastsdk.service_specification_loader.spec_loader import _load_from_runpod_serverless_server, load_spec
from fastsdk.service_specification_loader.replicate_loader import parse_replicate_model_ref

from fastsdk.sdk_factory.sdk_factory import generate_stub as _generate_stub_file
from typing import Union, Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path
import uuid


if TYPE_CHECKING:
    from fastsdk.fastClient import FastClient
    from fastsdk.service_interaction import ApiJob


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
        if self._api_job_manager:
            self._api_job_manager.service_registry = value

    @property
    def api_job_manager(self) -> ApiJobManager:
        if self._api_job_manager is None:
            self._api_job_manager = ApiJobManager(self.service_registry, progress_verbosity=self._progress_verbosity)
        return self._api_job_manager

    @api_job_manager.setter
    def api_job_manager(self, value: ApiJobManager):
        self._api_job_manager = value

    # ---- Service Inspection (pure, no registry side effects) ----
    @staticmethod
    def inspect_service(
        spec_source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        service_id: Optional[str] = None,
        service_address: Optional[str] = None,
        service_name: Optional[str] = None,
        category: Union[str, List[str]] = None,
        family_id: Optional[str] = None,
        used_models: Union[ModelDefinition, List[ModelDefinition], None] = None,
        specification: Optional[str] = None,
        description: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> ServiceDefinition:
        """
        Load and parse a service into a ServiceDefinition without adding it to the registry.
        
        Args:
            spec_source: What to inspect. Can be:
                - a URL ("http://localhost:8009", an openapi.json URL, a RunPod endpoint URL)
                - a Replicate model reference ("replicate:owner/name", "https://replicate.com/owner/name", "owner/name")
                - a file path to an openapi.json
                - an already loaded spec dict or a ServiceDefinition
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service name override
            category: Optional category assignment
            family_id: Optional family assignment
            used_models: Optional models used by service
            specification: Optional specification type override (e.g. "openapi", "runpod", "replicate")
            description: Optional description override
            api_key: Required for RunPod and Replicate sources, optional for others
            
        Returns:
            ServiceDefinition - inspect it, modify it, then register it or generate a stub from it.
        """
        address_resolved_by_loader = False
        if isinstance(spec_source, ServiceDefinition):
            service_def = spec_source
        else:
            replicate_ref = parse_replicate_model_ref(spec_source)
            if replicate_ref:
                from fastsdk.service_specification_loader.replicate_loader import load_replicate_service
                service_def = load_replicate_service(replicate_ref, api_key=api_key)
                address_resolved_by_loader = True
            else:
                # Load and parse the specification
                loaded_spec = load_spec(spec_source, api_key=api_key)
                service_def = parse_service_definition(loaded_spec)
        
        # Apply overrides
        if service_id:
            service_def.id = service_id
        elif not service_def.id:
            service_def.id = "gen-" + str(uuid.uuid4())
            
        if service_name:
            service_def.display_name = service_name
        elif not service_def.display_name:
            service_def.display_name = "unnamed_service_" + service_def.id

        if specification:
            service_def.specification = specification.lower()

        if service_address:
            service_def.service_address = create_service_address(service_address, service_def.specification)
        elif not address_resolved_by_loader and isinstance(spec_source, str) and "http" in spec_source:
            service_def.service_address = create_service_address(spec_source, None)

        if category:
            service_def.category = [category] if isinstance(category, str) else category
        if family_id:
            service_def.family_id = family_id
        if used_models:
            service_def.used_models = [used_models] if isinstance(used_models, ModelDefinition) else used_models
        if description:
            service_def.description = description

        return service_def

    @staticmethod
    def load_openapi_spec_from_runpod(runpod_url: str, api_key: str, return_api_job: bool = False) -> Union[ServiceDefinition, 'ApiJob']:
        """Load service definition from RunPod serverless server.
        If return_api_job is True, return an ApiJob object instead of a ServiceDefinition.
        """
        return _load_from_runpod_serverless_server(runpod_url, api_key, return_api_job)
 
    # ---- Service Registration ----
    def register_service(
        self,
        spec_source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        service_id: Optional[str] = None,
        service_address: Optional[str] = None,
        service_name: Optional[str] = None,
        category: Union[str, List[str], None] = None,
        family_id: Optional[str] = None,
        used_models: Union[ModelDefinition, List[ModelDefinition], None] = None,
        specification: Optional[str] = None,
        description: Optional[str] = None,
        api_key: Optional[str] = None,
        update_existing: bool = True
    ) -> ServiceDefinition:
        """
        Load a service and add it to the registry. Idempotent: registering a service whose ID
        already exists replaces the previous entry (re-running the same script never fails).
        
        Args:
            spec_source: Service definition or spec source (see inspect_service)
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service name override
            category: Optional category assignment
            family_id: Optional family assignment
            used_models: Optional models used by service
            specification: Optional specification type override
            description: Optional description override
            api_key: Required for RunPod and Replicate sources, optional for others
            update_existing: If True and a service with the same name and spec type is already
                registered, that entry is updated (its ID is kept) instead of adding a duplicate.
            
        Returns:
            The registered ServiceDefinition object
        """
        if isinstance(spec_source, ServiceDefinition):
            service_def = spec_source
        else:
            service_def = self.inspect_service(
                spec_source, service_id, service_address, service_name,
                category, family_id, used_models, specification, description, api_key
            )
            # Most specs (e.g. OpenAPI) don't embed a service ID, so every parse generates a fresh
            # one. Reuse the ID of an already registered service with the same name and spec type,
            # so re-runs update the existing entry and previously generated stubs stay valid.
            if update_existing and service_id is None and service_def.display_name:
                existing = self.service_registry.get_service(service_def.display_name)
                if existing is not None and existing.specification == service_def.specification:
                    service_def.id = existing.id

        # Upsert: replace an existing service with the same ID instead of raising.
        if service_def.id and self.service_registry.get_service(service_def.id):
            self.service_registry.remove_service(service_def.id)

        return self.service_registry.register_service(service_def)

    def update_service(self, service_id_or_name: str, **kwargs) -> Optional[ServiceDefinition]:
        """
        Update a service definition's attributes.
        Args:
            service_id_or_name: Service ID or display name
            **kwargs: Attributes to update. Unpack your **service_def to update all attributes.
            
        Returns:
            Updated ServiceDefinition if found, None otherwise
        """
        for key, value in kwargs.items():
            if key == "service_address" and isinstance(value, str):
                kwargs[key] = create_service_address(value, None)
        return self.service_registry.update_service(service_id_or_name, **kwargs)

    def get_service(self, service_id_or_name: str) -> Optional[ServiceDefinition]:
        """
        Get an already registered service by ID or name.
        
        Args:
            service_id_or_name: Service ID or display name
            
        Returns:
            ServiceDefinition if found, None otherwise
        """
        return self.service_registry.get_service(service_id_or_name)

    # ---- Client / Stub Creation ----
    def generate_stub(
        self,
        source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        save_path: Optional[str] = None,
        class_name: Optional[str] = None,
        template: Optional[str] = None,
        **kwargs
    ) -> FastStub:
        """
        Generate a Python client stub file (.py) for a service and register the service in the registry.
        
        Args:
            source: Service source (URL, file path, spec dict, ServiceDefinition, or a registered service ID/name)
            save_path: Path (file or directory) to save the generated file. Defaults to the current directory.
            class_name: Name for the generated class. Defaults to the service name.
            template: Optional custom Jinja2 template path
            **kwargs: Additional arguments for service loading (e.g. api_key, service_name)
            
        Returns:
            GeneratedStub with .path, .class_name, .service_definition and .client()
        """
        # Get or load service definition
        service_def = source
        if isinstance(source, str):
            service_def = self.get_service(source)
            if not isinstance(service_def, ServiceDefinition):
                service_def = self.register_service(source, **kwargs)
        else:
            service_def = self.register_service(source, **kwargs)

        if not isinstance(service_def, ServiceDefinition):
            raise ValueError("Invalid service source")
        
        return _generate_stub_file(service_def, save_path, class_name, template)

    def connect(
        self,
        source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        api_key: Optional[str] = None,
        **kwargs
    ) -> 'FastClient':
        """
        Connect to a service and return a ready-to-use client - no code generation involved.
        The service is registered temporarily and removed again when the client is deleted.
        
        Args:
            source: Service source (URL, file path, spec dict, ServiceDefinition or Replicate model ref)
            api_key: Optional API key for the service
            **kwargs: Additional arguments for service loading
            
        Returns:
            FastClient instance. Call endpoints via client.endpoint_name(...) after stub generation,
            or generically via client.submit_job("/endpoint", **params).
        """
        from fastsdk.fastClient import FastClient
        return FastClient(source, api_key=api_key, temporary=True, **kwargs)
