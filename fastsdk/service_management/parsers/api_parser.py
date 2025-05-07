from typing import Dict, Any, Optional, List, Union
from fastsdk.service_management.parsers.spec_loader import load_spec
from fastsdk.service_management.parsers.factory import (
    create_service_definition,
    create_endpoint_definition,
    create_endpoint_parameter
)
from fastsdk.service_management.service_definition import (
    ServiceDefinition,
    EndpointDefinition,
    EndpointParameter,
    ServiceSpecification,
    ParameterType
)


class OpenAPIParser:
    """Parser for OpenAPI specifications that generates service definitions."""

    def __init__(self, spec_source: Union[str, Dict[str, Any]]):
        """
        Initialize the parser with an OpenAPI specification source.

        Args:
            spec_source: Path/URL to openapi.json file or loaded spec dictionary.
        """
        self.spec_source = spec_source  # Keep track of the original source
        try:
            self.spec = load_spec(spec_source)
        except Exception as e:
            raise ValueError(f"Failed to load or parse OpenAPI spec from {spec_source}: {e}")

        self.service_definition: Optional[ServiceDefinition] = None
        # Store components/schemas for reference resolution
        self._components = self.spec.get('components', {})
        self._schemas = self._components.get('schemas', {})

    def parse(self) -> ServiceDefinition:
        """Parse the OpenAPI specification and return a ServiceDefinition."""
        # Extract basic service information
        info = self.spec.get('info', {})
        specification = self._determine_specification(info)

        # Use the factory function to create a ServiceDefinition
        self.service_definition = create_service_definition(
            id=info.get('x-service-id'),  # Socaity specific extension?
            display_name=info.get('title'),
            description=info.get('description'),
            short_desc=info.get('summary'),
            specification=specification,
            source_identifier=self.spec_source if isinstance(self.spec_source, str) else None,
            schemas=self._schemas  # Store schemas directly in the definition
        )

        # Parse paths and endpoints
        paths = self.spec.get('paths', {})
        for path, path_data in paths.items():
            # Process common parameters for the path
            common_parameters_data = path_data.get('parameters', [])
            common_parameters = [self._parse_parameter(param_data) for param_data in common_parameters_data if self._parse_parameter(param_data) is not None] # Filter out None params

            for method, method_data in path_data.items():
                # Skip non-method keys like 'parameters'
                if method.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'trace']:
                    continue
                endpoint = self._parse_endpoint(path, method, method_data, common_parameters)
                if endpoint: # Ensure endpoint parsing was successful
                    self.service_definition.endpoints.append(endpoint)

        return self.service_definition

    def _determine_specification(self, info: Dict[str, Any]) -> ServiceSpecification:
        """Determine the service specification type based on the OpenAPI info and content."""
        # 1. Explicit 'fast-task-api' key in info (highest priority)
        if "fast-task-api" in info:
            return "fasttaskapi"

        # 2. Check for FastTaskAPI specific schemas like JobResult or MediaFile models
        if self._schemas:
            schema_names = {name.lower() for name in self._schemas.keys()}
            if 'jobresult' in schema_names or any(s.endswith('filemodel') for s in schema_names):
                return "fasttaskapi"

        # 3. Heuristics based on info section keywords
        info_title = info.get('title', '').lower()
        info_desc = info.get('description', '').lower()
        info_text = info_title + " " + info_desc

        # Check for combined patterns from legacy code
        if "fast-task-api" in info_text and "runpod" in info_text:
            return "runpod"
        if 'fast-task-api' in info_text or 'fasttaskapi' in info_text:
            return "fasttaskapi"
        if 'socaity' in info_text:
            return "socaity"
        if 'openai' in info_title:
            return "openai"
        if 'replicate' in info_title:
            return "replicate"
        if 'runpod' in info_title:
            return "runpod"

        # 4. Heuristic based on spec source if available
        if isinstance(self.spec_source, str):
            if "api.socaity.ai" in self.spec_source:
                return "socaity"
            if "runpod" in self.spec_source.lower():
                return "runpod"
            if "replicate" in self.spec_source.lower():
                return "replicate"

        # 5. Default to 'openapi' if none of the above match
        return "openapi"

    def _resolve_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        """Resolve a $ref pointer within the spec."""
        if not ref or not ref.startswith('#/'):
            return None
        parts = ref[2:].split('/')
        current = self.spec
        try:
            for part in parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return None

    def _parse_endpoint(self, path: str, method: str, data: Dict[str, Any], common_parameters: List[EndpointParameter]) -> Optional[EndpointDefinition]:
        """Parse a single endpoint from the OpenAPI spec."""
        try:
            endpoint = create_endpoint_definition(
                id=data.get('operationId'),
                path=path,
                # display_name=data.get('summary'),
                description=data.get('description'),
                short_desc=data.get('summary'),
                method=method.lower(),
                timeout_s=data.get('x-timeout') # Example extension
            )

            # Add common parameters first
            endpoint.parameters.extend(common_parameters)

            # Parse operation-specific parameters
            for param_data in data.get('parameters', []):
                # Resolve $ref if present
                if '$ref' in param_data:
                    resolved_param = self._resolve_ref(param_data['$ref'])
                    if resolved_param:
                        param_data = resolved_param
                    else:
                        continue  # Skipping unresolved param ref

                param = self._parse_parameter(param_data)
                if param:  # Check if parameter parsing was successful
                    endpoint.parameters.append(param)

            # Parse request body
            request_body_data = data.get('requestBody')
            if request_body_data and isinstance(request_body_data, dict):
                # Resolve $ref for requestBody if present
                if '$ref' in request_body_data:
                    resolved_body = self._resolve_ref(request_body_data['$ref'])
                    if resolved_body:
                        request_body_data = resolved_body
                    else:
                        request_body_data = None  # Cannot proceed without resolved body

                if request_body_data:
                    content = request_body_data.get('content', {})
                    required = request_body_data.get('required', False)
                    description = request_body_data.get('description')

                    # Handle multipart/form-data (common for file uploads)
                    form_schema_data = content.get('multipart/form-data', {}).get('schema')
                    if form_schema_data:
                        if '$ref' in form_schema_data:
                            resolved_schema = self._resolve_ref(form_schema_data['$ref'])
                            if resolved_schema:
                                form_schema_data = resolved_schema
                            else:
                                form_schema_data = None # Cannot proceed

                        if form_schema_data and form_schema_data.get('type') == 'object':
                            for prop_name, prop_schema in form_schema_data.get('properties', {}).items():
                                prop_required = prop_name in form_schema_data.get('required', [])
                                param = self._create_param_from_schema(prop_name, prop_schema, prop_required, "body", description=prop_schema.get('description'))
                                if param:
                                    endpoint.parameters.append(param)

                    # Handle application/json
                    json_schema_data = content.get('application/json', {}).get('schema')
                    if json_schema_data:
                        if '$ref' in json_schema_data:
                            resolved_schema = self._resolve_ref(json_schema_data['$ref'])
                            if resolved_schema:
                                json_schema_data = resolved_schema
                            else:
                                json_schema_data = None # Cannot proceed

                        if json_schema_data:
                            body_param = create_endpoint_parameter(
                                name="body",
                                location="body",
                                required=required,
                                description=description,
                                param_schema=json_schema_data,
                                type="object" # Assuming json body is an object
                            )
                            endpoint.parameters.append(body_param)

                    # TODO: Handle other content types like application/x-www-form-urlencoded if needed

            # Parse responses (just store them for now)
            endpoint.responses = data.get('responses', {})

            return endpoint
        except Exception as e:
            print(f"Warning: Failed to parse endpoint {method.upper()} {path}: {e}")
            return None # Return None if endpoint parsing fails

    def _parse_parameter(self, param_data: Dict[str, Any]) -> Optional[EndpointParameter]:
        """Parse a single parameter (query, path, header, cookie) from the OpenAPI spec."""
        try:
            name = param_data.get('name')
            location = param_data.get('in', 'body')
            required = param_data.get('required', False)
            description = param_data.get('description')
            schema = param_data.get('schema', {})

            # Resolve $ref for schema if present
            if '$ref' in schema:
                resolved_schema = self._resolve_ref(schema['$ref'])
                if resolved_schema:
                    schema = resolved_schema
                else:
                    schema = {}  # Cannot proceed without schema

            return self._create_param_from_schema(name, schema, required, location, description)
        except Exception as e:
            return None

    def _get_parameter_type_from_schema(self, schema: Dict[str, Any]) -> Union[ParameterType, List[ParameterType]]:
        """Determines the ParameterType based on schema properties, handling common types and media types."""
      
        param_type = schema.get('type')
        # 1. Handle array types
        if param_type == 'array':
            items_schema = schema.get('items', {})
            if isinstance(items_schema, dict):
                item_type = self._get_parameter_type_from_schema(items_schema)
                return ['array', item_type]
            return ['array', 'object']  # fallback if items schema is not a dict

        # 2. Handle strings that might be media file types
        if param_type == 'string' and schema.get('format') in ['binary', 'byte']:  # starlette upload file
            return ['file', 'string', 'bytes']

        # 3. Handle direct types
        if param_type in ParameterType.__args__:
            return param_type

        # 3. Check 'anyOf' for specific model references (FastTaskAPI style)
        if 'anyOf' in schema:
            file_formats = set()
            for option in schema.get('anyOf', []):
                if '$ref' in option:
                    ref_path = option['$ref']
                    ref_name = ref_path.split('/')[-1].lower()
                    if 'imagefilemodel' in ref_name:
                        file_formats.add('image')
                    elif 'videofilemodel' in ref_name:
                        file_formats.add('video')
                    elif 'audiofilemodel' in ref_name:
                        file_formats.add('audio')
                    elif 'filemodel' in ref_name:
                        file_formats.add('file')
                    # Check for format: binary within anyOf
                elif option.get('type') == 'string' and option.get('format') == 'binary':
                    file_formats.add('file')

            if len(file_formats) == 1:
                return [file_formats.pop(), 'string', 'bytes']
            elif file_formats:
                return [*file_formats, 'string', 'bytes']

        # 4. Handle object references
        if '$ref' in schema:
            return 'object'

        # 5. Fallback for unknown types
        return "object"

    def _create_param_from_schema(
        self,
        name: str,
        schema: Dict[str, Any],
        required: bool,
        location: str,
        description: Optional[str] = None
    ) -> EndpointParameter:
        """Creates an EndpointParameter with type resolution."""
        param_type = self._get_parameter_type_from_schema(schema)
        default_value = schema.get('default')

        return create_endpoint_parameter(
            name=name,
            type=param_type,
            required=required,
            default=default_value,
            location=location,  # Already validated or derived
            description=description or schema.get('description'),
            param_schema=schema  # Pass the original or resolved schema
        )
