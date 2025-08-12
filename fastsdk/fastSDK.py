from fastsdk.service_management import ServiceManager
from fastsdk.service_definition import ServiceDefinition, ModelDefinition
from fastsdk.service_interaction import ApiJobManager
from fastsdk.service_specification_loader.spec_loader import _load_from_runpod_serverless_server, load_spec
from fastsdk.service_specification_loader.parsers import parse_service_definition
from fastsdk.sdk_factory.sdk_factory import create_sdk
from typing import Union, Optional, Dict, Any, List, overload, TYPE_CHECKING
from pathlib import Path
from fastsdk.service_specification_loader.parsers.service_adress_parser import create_service_address
import uuid

if TYPE_CHECKING:
    from fastsdk.fastClient import TemporaryFastClient
    from fastsdk.service_interaction import ApiJob


class FastSDK:
    _instance: 'FastSDK' = None
    
    def __new__(cls) -> 'FastSDK':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._service_manager = None
            self._api_job_manager = None
            self._initialized = True

    @property
    def service_manager(self) -> ServiceManager:
        if self._service_manager is None:
            self._service_manager = ServiceManager()
        return self._service_manager

    @service_manager.setter
    def service_manager(self, value: ServiceManager):
        self._service_manager = value
        if self._api_job_manager:
            self._api_job_manager.service_manager = value

    @property
    def api_job_manager(self) -> ApiJobManager:
        if self._api_job_manager is None:
            self._api_job_manager = ApiJobManager(self.service_manager)
        return self._api_job_manager

    @api_job_manager.setter
    def api_job_manager(self, value: ApiJobManager):
        self._api_job_manager = value

    # ---- Service Definition Loading Methods ----
    @overload
    def load_service_definition(self, spec_source: str) -> ServiceDefinition:
        """Load a service definition from spec source."""
        ...

    @overload
    def load_service_definition(self, spec_source: Union[Path, Dict[str, Any]]) -> ServiceDefinition:
        """Load a service definition from spec source."""
        ...

    @overload
    def load_service_definition(
        self,
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
        Load a service definition from various sources without adding it to the service manager.
        Overwrite attributes loaded from spec source.
        Args:
            spec_source: Service definition or spec source
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service name override
            category: Optional category assignment
            family_id: Optional family assignment
            used_models: Optional models used by service
            specification: Optional specification type override
            description: Optional description override
            api_key: Required for RunPod URLs, optional for others
        """
        ...

    def load_service_definition(
        self,
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
        Load a service definition from various sources without adding it to the service manager.
        
        Args:
            spec_source: OpenAPI spec source (URL, file path, dict, or ServiceDefinition)
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service name override
            category: Optional category assignment
            family_id: Optional family assignment
            used_models: Optional models used by service
            specification: Optional specification type override
            description: Optional description override
            api_key: Required for RunPod URLs, optional for others
            
        Returns:
            ServiceDefinition object ready to be added to service manager
        """
        # Handle ServiceDefinition objects
        if isinstance(spec_source, ServiceDefinition):
            service_def = spec_source
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
        elif isinstance(spec_source, str) and "http" in spec_source:
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

    def load_openapi_spec_from_runpod(self, runpod_url: str, api_key: str, return_api_job: bool = False) -> Union[ServiceDefinition, 'ApiJob']:
        """Load service definition from RunPod serverless server.
        If return_api_job is True, return an ApiJob object instead of a ServiceDefinition.
        """
        return _load_from_runpod_serverless_server(runpod_url, api_key, return_api_job)
 
    # ---- Service Adding Methods ----
    @overload
    def add_service(self, spec_source: str) -> ServiceDefinition:
        """
        Add a service from any source or file.
        """
        ...

    @overload
    def add_service(self, spec_source: Union[str, Path, Dict[str, Any]], api_key: Optional[str] = None) -> ServiceDefinition:
        """
        Add a service from spec source.
        api_key is required for RunPod serverless endpoints if the openapi.json specification needs to be fetched from the serverless endpoint.
        """
        ...

    @overload
    def add_service(self, service_def: ServiceDefinition) -> ServiceDefinition:
        """Add a service from ServiceDefinition object."""
        ...

    @overload
    def add_service(
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
        api_key: Optional[str] = None
    ) -> ServiceDefinition:
        """
        Overwrite attributes loaded from spec source when adding a service to the service manager.
        Args:
            spec_source: Service definition or spec source
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service name override
            category: Optional category assignment
            family_id: Optional family assignment
            used_models: Optional models used by service
            specification: Optional specification type override
            description: Optional description override
            api_key: Required for RunPod URLs, optional for others
            
        Returns:
            Added ServiceDefinition object
        """
        ...

    def add_service(
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
        api_key: Optional[str] = None
    ) -> ServiceDefinition:
        """
        Load and add a service to the service manager.
        
        Args:
            spec_source: Service definition or spec source
            service_id: Optional service ID override
            service_address: Optional service address override
            service_name: Optional service name override
            category: Optional category assignment
            family_id: Optional family assignment
            used_models: Optional models used by service
            specification: Optional specification type override
            description: Optional description override
            api_key: Required for RunPod URLs, optional for others
            
        Returns:
            Added ServiceDefinition object
        """
        # If already a ServiceDefinition, add it directly
        if isinstance(spec_source, ServiceDefinition):
            return self.service_manager.add_service(spec_source)
        
        # Load the service definition first
        service_def = self.load_service_definition(
            spec_source, service_id, service_address, service_name,
            category, family_id, used_models, specification, description, api_key
        )
        
        # Add to service manager
        return self.service_manager.add_service(service_def)

    def update_service(self, service_id_or_name: str, **kwargs) -> Optional[ServiceDefinition]:
        """
        Update a service definition's attributes.
        Args:
            service_id_or_name: Service ID or display name
            **kwargs: Attributes to update. Unpack your **service_def to update all attributes.
            
        Returns:
            Updated ServiceDefinition if found, None otherwise
        """
        return self.service_manager.update_service(service_id_or_name, **kwargs)

    def get_service(self, service_id_or_name: str) -> Optional[ServiceDefinition]:
        """
        Get a already added service by ID or name.
        
        Args:
            service_id_or_name: Service ID or display name
            
        Returns:
            ServiceDefinition if found, None otherwise
        """
        return self.service_manager.get_service(service_id_or_name)

    # ---- Client Creation Methods ----
    
    @overload
    def create_sdk(self, spec_source: Union[Path, Dict[str, Any]], api_key: str = None) -> str:
        """Create a client from spec source."""
        ...

    @overload
    def create_sdk(self, service_def: ServiceDefinition, api_key: str = None) -> str:
        """Create a client from ServiceDefinition."""
        ...

    @overload
    def create_sdk(self, service_id_or_name: str, api_key: str = None) -> str:
        """Create a client from service ID or name."""
        ...

    def create_sdk(
        self,
        source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        save_path: Optional[str] = None,
        class_name: Optional[str] = None,
        template: Optional[str] = None,
        **kwargs
    ) -> tuple[str, str, ServiceDefinition]:
        """
        Create a Python SDK file for a service.
        
        Args:
            source: Service source (spec, ServiceDefinition, or service ID/name)
            save_path: Path to save the generated file
            class_name: Name for the generated class
            template: Optional custom template path
            **kwargs: Additional arguments for service loading
            
        Returns:
            Tuple of (file_path, class_name, service_definition)
        """
        # Get or load service definition
        service_def = source
        if isinstance(source, str):
            service_def = self.get_service(source)
            if not isinstance(service_def, ServiceDefinition):
                service_def = self.load_service_definition(source, **kwargs)
        else:
            service_def = self.load_service_definition(source, **kwargs)

        if not isinstance(service_def, ServiceDefinition):
            raise ValueError("Invalid service source")
        
        return create_sdk(service_def, save_path, class_name, template)

    def create_temporary_client(
        self,
        spec_source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        api_key: Optional[str] = None,
        **kwargs
    ) -> 'TemporaryFastClient':
        """
        Create a temporary client that will be automatically removed when deleted.
        
        Args:
            spec_source: Service source to create temporary client for
            api_key: Optional API key for the service
            **kwargs: Additional arguments for service loading
            
        Returns:
            TemporaryFastClient instance
        """
        from fastsdk.fastClient import TemporaryFastClient
        return TemporaryFastClient(spec_source, api_key)
