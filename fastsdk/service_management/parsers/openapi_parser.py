from typing import Dict, Any, Optional, List
import hashlib
import json

from fastsdk.service_management.parsers.base_parser import BaseParser
from fastsdk.service_management.parsers.factory import (
    create_service_definition,
    create_endpoint_definition
)
from fastsdk.service_management.service_definition import (
    ServiceDefinition,
    EndpointDefinition
)


class OpenAPIParser(BaseParser):
    """OpenAPI parser for general OpenAPI specification parsing."""

    def __init__(self, spec: Dict[str, Any]):
        super().__init__(spec)
        self.service_definition: Optional[ServiceDefinition] = None

    def parse(self) -> ServiceDefinition:
        """Parse the OpenAPI specification into a ServiceDefinition."""
        info = self.spec.get('info', {})
        
        self.service_definition = create_service_definition(
            display_name=info.get('title'),
            description=info.get('description'),
            short_desc=info.get('summary'),
            specification="openapi",  # Default, will be overridden by subclasses
            schemas=self._schemas,
            version=self._create_version_hash()
        )

        for path, path_data in self.spec.get('paths', {}).items():
            path_params = self.parse_parameters(path_data)
            for method, method_data in path_data.items():
                if method.lower() in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                    endpoint = self._parse_endpoint(path, method.lower(), method_data, path_params)
                    if endpoint:
                        self.service_definition.endpoints.append(endpoint)

        return self.service_definition

    def _parse_endpoint(
        self,
        path: str,
        method: str,
        method_data: Dict[str, Any],
        path_params: List = None
    ) -> Optional[EndpointDefinition]:
        """Parse a single endpoint from the OpenAPI specification."""
        endpoint = create_endpoint_definition(
            id=method_data.get('operationId'),
            path=path,
            description=method_data.get('description'),
            short_desc=method_data.get('summary'),
            method=method,
            timeout_s=method_data.get('x-timeout')
        )
        
        all_params = path_params or []
        all_params.extend(self.parse_parameters(method_data))
        all_params.extend(self.parse_body_params(method_data, path))

        # Deduplicate params by (name, location)
        seen = set()
        for param in all_params:
            key = (param.name, param.location if param.location != 'body' else 'body')
            if key not in seen:
                endpoint.parameters.append(param)
                seen.add(key)

        endpoint.responses = method_data.get('responses', {})
        return endpoint

    def _create_version_hash(self) -> str:
        """Create a version hash from the specification."""
        return hashlib.sha1(json.dumps(self.spec, sort_keys=True).encode()).hexdigest()
