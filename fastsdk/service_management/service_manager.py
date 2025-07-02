from typing import Dict, Optional, Union, Any, List, Iterator
from pathlib import Path
from fastsdk.service_management.service_definition import (
    ServiceDefinition, ModelDefinition, ServiceCategory, ServiceFamily, EndpointDefinition, ServiceAddress
)
from fastsdk.service_management.parsers import parse_service_definition
from fastsdk.service_management.parsers.service_adress_parser import create_service_address
from fastsdk.service_management.service_store.IServiceStore import IServiceStore
import uuid
from fastsdk.utils import normalize_name_for_py
    

class ServiceManager:
    """
    Central manager for all service-related entities.
    Manages ServiceDefinitions, ServiceCategories, ServiceFamilies, and ModelDefinitions.
    Maintains relationships between these entities.
    """
    def __init__(self, service_store: IServiceStore = None):
        self.service_store = service_store

        self._services: Dict[str, ServiceDefinition] = {}
        self._categories: Dict[str, ServiceCategory] = {}
        self._families: Dict[str, ServiceFamily] = {}
        self._models: Dict[str, ModelDefinition] = {}
        
        # Normalized name mappings for easier lookup
        self._service_names: Dict[str, str] = {}  # normalized name -> id
        self._category_names: Dict[str, str] = {}
        self._family_names: Dict[str, str] = {}
        self._model_names: Dict[str, str] = {}

        # Load services from store if available
        if self.service_store:
            for service in self.service_store.list_services():
                self._services[service.id] = service
                if service.display_name:
                    normalized = normalize_name_for_py(service.display_name)
                    self._service_names[normalized] = service.id

    def add_service(
        self,
        spec_source: Union[str, Path, Dict[str, Any], ServiceDefinition],
        service_id: Optional[str] = None,
        service_address: Optional[str] = None,
        service_name: Optional[str] = None,
        category: Union[str, List[str]] = None,
        family_id: str = None,
        used_models: Union[ModelDefinition, List[ModelDefinition]] = None,
        specification: str = None,
        description: str = None
    ) -> ServiceDefinition:
        """
        Add a new service definition from an OpenAPI specification source using OpenAPIParser.
        
        Args:
            spec_source: Path, URL to OpenAPI JSON, service definition file or loaded JSON dictionary.
            service_id: Optional explicit ID to assign to the service,
                overriding any ID found in the spec or generated.
            service_address: Optional address to use for the service. If not provided and spec_sources is an url, the url will be used.
            service_name: Optional name to assign to the service. Overrides any name found in the spec.
            category: Optional category to assign to the service. Overrides any category found in the spec.
            family_id: Optional family to assign to the service. Overrides any family found in the spec.
            used_models: Optional models to assign to the service. Overrides any models found in the spec.
            specification: Optional to guide the service manager additionally in resolving service adresses. Overrides any specification determined by the spec.
        Returns:
            The added ServiceDefinition object.
            
        Raises:
            ValueError: If the service ID (either provided or parsed) is already registered,
                        or if the spec cannot be parsed.
        """
        service_def = parse_service_definition(spec_source)

        if service_id is not None:
            service_def.id = service_id
    
        if not service_def.id:
            service_def.id = "gen-" + str(uuid.uuid4())
            
        if service_name:
            service_def.display_name = service_name

        if not service_name and not service_def.display_name:
            service_def.display_name = "unnamed_service_" + service_def.id

        # Add normalized name mapping using display_name from the parsed definition
        normalized = normalize_name_for_py(service_def.display_name)
        # Check for potential name conflicts before adding
        if normalized in self._service_names and self._service_names[normalized] != service_def.id:
            print(f"Service name '{service_def.display_name}' (normalized: '{normalized}') conflicts with existing service ID '{self._service_names[normalized]}'. Overwriting mapping.")
        self._service_names[normalized] = service_def.id

        if specification and isinstance(specification, str):
            service_def.specification = specification.lower()

        if service_address is not None and isinstance(service_address, str):
            service_def.service_address = create_service_address(service_address, service_def.specification)
        elif service_address is None and isinstance(spec_source, str) and spec_source.startswith(('http://', 'https://')):
            service_def.service_address = create_service_address(spec_source, service_def.specification)
        elif isinstance(service_address, ServiceAddress):
            service_def.service_address = service_address

        if category:
            service_def.category = [category] if isinstance(category, str) else category
        if family_id:
            service_def.family_id = family_id
        if used_models:
            service_def.used_models = [used_models] if isinstance(used_models, ModelDefinition) else used_models
        if description:
            service_def.description = description

        # Store the service definition
        self._services[service_def.id] = service_def

        # Save to store if available
        if self.service_store:
            self.service_store.save_service(service_def)

        # Link to family, categories, and models based on IDs parsed
        self._link_service_dependencies(service_def)

        return service_def
    
    def _link_service_dependencies(self, service_def: ServiceDefinition):
        """Helper to link service to existing families, categories, and register its models."""
        # Link to family if specified and family exists (no placeholder creation here)
        if service_def.family_id and service_def.family_id in self._families:
            # The link is implicit via the ID stored in service_def
            pass

        # Link to categories if specified
        if service_def.category:
            for category_id in service_def.category:
                if category_id not in self._categories:
                    # Option: Create placeholder category or log warning?
                    # Creating placeholder for now to maintain consistency
                    # print(f"Warning: Category ID '{category_id}' referenced by service '{service_def.id}' not found. Creating placeholder.")
                    self._categories[category_id] = ServiceCategory(id=category_id)
                    # Add name mapping for placeholder
                    self._category_names[normalize_name_for_py(f"Category {category_id}")] = category_id

        # Register models used by the service if they aren't already known
        # The parser doesn't create ModelDefinition objects yet, needs update there or here.
        # Placeholder: Assuming service_def.used_models contains necessary info if populated by parser later.
        if service_def.used_models:
            for model_info in service_def.used_models: # Assuming used_models is list of dicts/Models for now
                model_id = model_info.get('id') if isinstance(model_info, dict) else getattr(model_info, 'id', None)
                if model_id and model_id not in self._models:
                    # Need to create ModelDefinition from model_info
                    # This logic depends on how parser stores model info
                    # Placeholder: Create a basic ModelDefinition
                    model_name = model_info.get('display_name') if isinstance(model_info, dict) else getattr(model_info, 'display_name', None)
                    model_def = ModelDefinition(id=model_id, display_name=model_name or f"Model {model_id}")
                    self._models[model_id] = model_def
                    if model_def.display_name:
                        self._model_names[normalize_name_for_py(model_def.display_name)] = model_id

    def get_service(self, id_or_name: str) -> Optional[ServiceDefinition]:
        """
        Get a service definition by its ID or display name. 
        Precondition: the service must have been added to the ServiceManager/ServiceStore previously.
        First checks the in-memory cache, then falls back to the ServiceStore if available.
        
        Args:
            id_or_name: Service ID or display name
            
        Returns:
            ServiceDefinition if found, None otherwise
        """
        # Direct ID lookup in cache
        if id_or_name in self._services:
            return self._services[id_or_name]
        
        # Normalized name lookup in cache
        normalized = normalize_name_for_py(id_or_name)
        if normalized in self._service_names:
            service_id = self._service_names[normalized]
            return self._services[service_id]
        
        # If not found in cache and service store is available, try loading from service store
        if self.service_store:
            service = self.service_store.load_service(id_or_name)
            if service:
                return self.add_service(service)

            # Try loading by normalized name if direct ID lookup failed
            if normalized != id_or_name:
                service = self.service_store.load_service(normalized)
                if service:
                    return self.add_service(service)
        
        return None
    
    def update_service(
        self,
        id_or_name: str,
        persist_changes: bool = True,
        **kwargs
    ) -> Optional[ServiceDefinition]:
        """
        Update a service definition's attributes.
        
        Args:
            id_or_name: Service ID or display name
            persist_changes: If True, the changes will be saved to the service store.
            **kwargs: Attributes to update
            
        Returns:
            Updated ServiceDefinition if found, None otherwise
        """
        service = self.get_service(id_or_name)
        if not service:
            return None
        
        # Update attributes
        for key, value in kwargs.items():
            if hasattr(service, key):
                if key == 'service_address':
                    service.service_address = create_service_address(value)
                elif key == 'display_name':
                    # Remove old normalized name mapping
                    if service.display_name:
                        oldnormalized = normalize_name_for_py(service.display_name)
                        self._service_names.pop(oldnormalized, None)
                    # Add new normalized name mapping
                    normalized = normalize_name_for_py(value)
                    self._service_names[normalized] = service.id
                else:
                    setattr(service, key, value)
        
        self._services[service.id] = service
        if persist_changes and self.service_store:
            self.service_store.save_service(service)

        return service
    
    def remove_service(self, id_or_name: str) -> bool:
        """
        Remove a service definition.
        
        Args:
            id_or_name: Service ID or display name
            
        Returns:
            True if removed, False if not found
        """
        service = self.get_service(id_or_name)
        if not service:
            return False
        
        # Remove from mappings
        self._services.pop(service.id)
        
        # Remove from store if available
        if self.service_store:
            self.service_store.delete_service(service.id)
        
        if service.display_name:
            normalized = normalize_name_for_py(service.display_name)
            self._service_names.pop(normalized, None)
        
        return True
    
    def list_services(self) -> List[ServiceDefinition]:
        """List all service definitions."""
        return list(self._services.values())
    
    def filter_services(self, **kwargs) -> List[ServiceDefinition]:
        """
        Filter services by their attributes.
        
        Args:
            **kwargs: Attribute name and value pairs to filter by
            
        Returns:
            List of matching services
        """
        result = []
        for service in self._services.values():
            match = True
            for attr, value in kwargs.items():
                if not hasattr(service, attr):
                    match = False
                    break
                
                attr_value = getattr(service, attr)
                if attr_value != value:
                    match = False
                    break
            
            if match:
                result.append(service)
        
        return result
    
    def get_services_by_family(self, family_id_or_name: str) -> List[ServiceDefinition]:
        """
        Get all services belonging to a specific family.
        
        Args:
            family_id_or_name: Family ID or display name
            
        Returns:
            List of services in the family
        """
        family = self.get_family(family_id_or_name)
        if not family:
            return []
        
        return [s for s in self._services.values() if s.family_id == family.id]
    
    def get_services_by_category(self, category_id_or_name: str) -> List[ServiceDefinition]:
        """
        Get all services belonging to a specific category.
        
        Args:
            category_id_or_name: Category ID or display name
            
        Returns:
            List of services in the category
        """
        category = self.get_category(category_id_or_name)
        if not category:
            return []
        
        return [s for s in self._services.values() if category.id in (s.category or [])]
    
    # ---- Service Category Methods ----
    
    def add_category(self, category: ServiceCategory) -> ServiceCategory:
        """
        Add a new service category.
        
        Args:
            category: ServiceCategory object
            
        Returns:
            Added ServiceCategory
            
        Raises:
            ValueError: If the category has no ID or is already registered
        """
        if not category.id:
            raise ValueError("Category must have an ID")
        
        if category.id in self._categories:
            raise ValueError(f"Category '{category.id}' is already registered")
        
        self._categories[category.id] = category
        
        if category.display_name:
            normalized = normalize_name_for_py(category.display_name)
            self._category_names[normalized] = category.id
        
        return category
    
    def get_category(self, id_or_name: str) -> Optional[ServiceCategory]:
        """
        Get a service category by its ID or display name.
        
        Args:
            id_or_name: Category ID or display name
            
        Returns:
            ServiceCategory if found, None otherwise
        """
        # Direct ID lookup
        if id_or_name in self._categories:
            return self._categories[id_or_name]
        
        # Normalized name lookup
        normalized = normalize_name_for_py(id_or_name)
        if normalized in self._category_names:
            category_id = self._category_names[normalized]
            return self._categories[category_id]
        
        return None
    
    def list_categories(self) -> List[ServiceCategory]:
        """List all service categories."""
        return list(self._categories.values())
    
    # ---- Service Family Methods ----
    
    def add_family(self, family: ServiceFamily) -> ServiceFamily:
        """
        Add a new service family.
        
        Args:
            family: ServiceFamily object
            
        Returns:
            Added ServiceFamily
            
        Raises:
            ValueError: If the family has no ID or is already registered
        """
        if not family.id:
            raise ValueError("Family must have an ID")
        
        if family.id in self._families:
            raise ValueError(f"Family '{family.id}' is already registered")
        
        self._families[family.id] = family
        
        if family.display_name:
            normalized = normalize_name_for_py(family.display_name)
            self._family_names[normalized] = family.id
        
        return family
    
    def get_family(self, id_or_name: str) -> Optional[ServiceFamily]:
        """
        Get a service family by its ID or display name.
        
        Args:
            id_or_name: Family ID or display name
            
        Returns:
            ServiceFamily if found, None otherwise
        """
        # Direct ID lookup
        if id_or_name in self._families:
            return self._families[id_or_name]
        
        # Normalized name lookup
        normalized = normalize_name_for_py(id_or_name)
        if normalized in self._family_names:
            family_id = self._family_names[normalized]
            return self._families[family_id]
        
        return None
    
    def list_families(self) -> List[ServiceFamily]:
        """List all service families."""
        return list(self._families.values())
    
    # ---- Model Definition Methods ----
    
    def add_model(self, model: ModelDefinition) -> ModelDefinition:
        """
        Add a new model definition.
        
        Args:
            model: ModelDefinition object
            
        Returns:
            Added ModelDefinition
            
        Raises:
            ValueError: If the model has no ID or is already registered
        """
        if not model.id:
            raise ValueError("Model must have an ID")
        
        if model.id in self._models:
            raise ValueError(f"Model '{model.id}' is already registered")
        
        self._models[model.id] = model
        
        if model.display_name:
            normalized = normalize_name_for_py(model.display_name)
            self._model_names[normalized] = model.id
        
        return model
    
    def get_endpoint(self, service_id_or_name: str, endpoint_id_or_name: str) -> Optional[EndpointDefinition]:
        """
        Get an endpoint definition by its ID or display name.
        """
        service_def = self.get_service(service_id_or_name)
        if not service_def:
            return None

        # add leading slash if not present
        probable_path = endpoint_id_or_name
        if not probable_path.startswith('/'):
            probable_path = f"/{probable_path}"

        endpoint_def = next((ep for ep in service_def.endpoints if ep.id == endpoint_id_or_name or ep.path == probable_path), None)
        return endpoint_def

    def get_model(self, id_or_name: str) -> Optional[ModelDefinition]:
        """
        Get a model definition by its ID or display name.
        
        Args:
            id_or_name: Model ID or display name
            
        Returns:
            ModelDefinition if found, None otherwise
        """
        # Direct ID lookup
        if id_or_name in self._models:
            return self._models[id_or_name]
        
        # Normalized name lookup
        normalized = normalize_name_for_py(id_or_name)
        if normalized in self._model_names:
            model_id = self._model_names[normalized]
            return self._models[model_id]
        
        return None
    
    def list_models(self) -> List[ModelDefinition]:
        """List all model definitions."""
        return list(self._models.values())
    
    # ---- Dict-like interface ----
    
    def __getitem__(self, id_or_name: str) -> ServiceDefinition:
        """
        Dict-like access to get a service by ID or name.
        
        Args:
            id_or_name: Service ID or display name
            
        Returns:
            ServiceDefinition
            
        Raises:
            KeyError: If service not found
        """
        service = self.get_service(id_or_name)
        if service is None:
            raise KeyError(f"Service '{id_or_name}' not found")
        return service
    
    def __setitem__(self, id_or_name: str, value: Union[ServiceDefinition, Union[str, Path, Dict[str, Any]]]) -> None:
        """
        Dict-like access to add a service.
        
        Args:
            id_or_name: Service ID or display name
            value: Either ServiceDefinition object or spec_source
            
        Raises:
            ValueError: If invalid value type
        """
        if isinstance(value, ServiceDefinition):
            # Set ID if not already set
            if not value.id:
                value.id = id_or_name
            # Add service directly
            if value.id not in self._services:
                self._services[value.id] = value
                if value.display_name:
                    normalized = normalize_name_for_py(value.display_name)
                    self._service_names[normalized] = value.id
            else:
                raise ValueError(f"Service '{value.id}' is already registered")
        elif isinstance(value, (str, Path, dict)):
            # Add service from spec source
            self.add_service(value, id_or_name)
        else:
            raise ValueError("Value must be a ServiceDefinition or a spec source (str, Path, or dict)")
    
    def __iter__(self) -> Iterator[str]:
        """
        Iterate over service IDs.
        
        Returns:
            Iterator of service IDs
        """
        return iter(self._services.keys())
    
    def __len__(self) -> int:
        """
        Get the number of services.
        
        Returns:
            Number of services
        """
        return len(self._services)
    
    def pop(self, id_or_name: str, default: Any = None) -> Optional[ServiceDefinition]:
        """
        Remove and return a service.
        
        Args:
            id_or_name: Service ID or display name
            default: Default value to return if service not found
            
        Returns:
            Removed ServiceDefinition or default value
        """
        service = self.get_service(id_or_name)
        if service is None:
            return default
        
        # Remove from mappings
        self._services.pop(service.id)
        
        # Remove from store if available
        if self.service_store:
            self.service_store.delete_service(service.id)
        
        if service.display_name:
            normalized = normalize_name_for_py(service.display_name)
            self._service_names.pop(normalized, None)
        
        return service
    
    def pretty_print(self, indent: int = 2) -> str:
        """
        Generate a pretty-printed representation of the services using Pydantic model serialization.
        
        Args:
            indent: Number of spaces for indentation
            
        Returns:
            Pretty-printed JSON string
        """
        # Create a dictionary to hold all entities
        result = {
            "services": {},
            "categories": {},
            "families": {},
            "models": {}
        }
        
        # Add services using model's model_dump method for serialization
        for service_id, service in self._services.items():
            result["services"][service_id] = service.model_dump(exclude_none=True)
        
        # Add categories
        for category_id, category in self._categories.items():
            result["categories"][category_id] = category.model_dump(exclude_none=True)
        
        # Add families
        for family_id, family in self._families.items():
            result["families"][family_id] = family.model_dump(exclude_none=True)
        
        # Add models
        for model_id, model in self._models.items():
            result["models"][model_id] = model.model_dump(exclude_none=True)
        
        # Use json dumps for pretty printing
        from json import dumps
        return dumps(result, indent=indent, sort_keys=True)


if __name__ == "__main__":
    sm = ServiceManager()
    sm.add_service("test/face2face_openapi_spec.json")
    sm.add_service("test/speechcraft_openapi_spec.json")
    #  sm.add_service("https://api.socaity.ai/openapi.json")
    # print(sm.pretty_print())
