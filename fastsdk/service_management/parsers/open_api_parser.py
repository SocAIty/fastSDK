from typing import Dict, Any, Optional, List, Union
import hashlib
import json

from fastsdk.service_management.parsers.spec_loader import load_spec
from fastsdk.service_management.parsers.factory import (
    create_service_definition,
    create_endpoint_definition
)
from fastsdk.service_management.service_definition import (
    ServiceDefinition,
    EndpointDefinition,
    ServiceSpecification
)
from fastsdk.service_management.parsers.schema_parsers.base_parser import BaseSchemaParser
from fastsdk.service_management.parsers.schema_parsers.cog_parser import CogSchemaParser
from fastsdk.service_management.parsers.schema_parsers.fasttaskapi_parser import FastTaskAPISchemaParser


class OpenAPIParser:
    """Main OpenAPI parser that delegates schema-specific parsing."""

    def __init__(self, spec_source: Union[str, Dict[str, Any]]):
        self.spec_source = spec_source
        try:
            self.spec = load_spec(spec_source)
        except Exception as e:
            raise ValueError(f"Failed to load or parse OpenAPI spec from {spec_source}: {e}")
        self._schemas = self.spec.get('components', {}).get('schemas', {})
        self.service_definition: Optional[ServiceDefinition] = None
        self._schema_parser: BaseSchemaParser = None

    def _get_schema_parser(self, specification: ServiceSpecification) -> BaseSchemaParser:
        parsers = {
            "cog": CogSchemaParser,
            "replicate": CogSchemaParser,
            "fasttaskapi": FastTaskAPISchemaParser
        }
        return parsers.get(specification, BaseSchemaParser)(self.spec, self._schemas)

    def _determine_specification(self, info: Dict[str, Any]) -> ServiceSpecification:
        title = info.get('title', '').lower()
        desc = info.get('description', '').lower()
        combined = title + " " + desc

        if "fast-task-api" in info:
            return "fasttaskapi"
        if self._schemas:
            names = {k.lower() for k in self._schemas}
            if 'jobresult' in names or any(name.endswith('filemodel') for name in names):
                return "fasttaskapi"
        if title == 'cog':
            return "cog"
        if "replicate" in self._source_url_lower():
            return "replicate"
        if "runpod" in combined or "runpod" in self._source_url_lower():
            return "runpod"
        if "socaity" in combined or "api.socaity.ai" in self._source_url_lower():
            return "socaity"
        if "openai" in title:
            return "openai"

        return "openapi"

    def _source_url_lower(self) -> str:
        return self.spec_source.lower() if isinstance(self.spec_source, str) else ""

    def parse(self) -> ServiceDefinition:
        info = self.spec.get('info', {})
        specification = self._determine_specification(info)
        self._schema_parser = self._get_schema_parser(specification)

        self.service_definition = create_service_definition(
            display_name=info.get('title'),
            description=info.get('description'),
            short_desc=info.get('summary'),
            specification=specification,
            source_identifier=self.spec_source if isinstance(self.spec_source, str) else None,
            schemas=self._schemas,
            version=self._create_version_hash()
        )

        for path, path_data in self.spec.get('paths', {}).items():
            path_params = self._schema_parser.parse_parameters(path_data)
            for method, method_data in path_data.items():
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
        endpoint = create_endpoint_definition(
            id=method_data.get('operationId'),
            path=path,
            description=method_data.get('description'),
            short_desc=method_data.get('summary'),
            method=method,
            timeout_s=method_data.get('x-timeout')
        )
        
        all_params = path_params or []
        all_params.extend(self._schema_parser.parse_parameters(method_data))
        all_params.extend(self._schema_parser.parse_body_params(method_data, path))

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
        return hashlib.sha1(json.dumps(self.spec, sort_keys=True).encode()).hexdigest()

