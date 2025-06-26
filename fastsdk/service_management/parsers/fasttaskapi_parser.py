from typing import Dict, Any, List, Union

from fastsdk.service_management.parsers.openapi_parser import OpenAPIParser
from fastsdk.service_management.service_definition import ParameterType, ServiceDefinition


class FastTaskAPIParser(OpenAPIParser):
    """Parser for FastTaskAPI services that extends OpenAPI with FastTaskAPI-specific schema parsing."""

    def parse(self) -> ServiceDefinition:
        """Parse the FastTaskAPI specification into a ServiceDefinition."""
        service_def = super().parse()
        service_def.specification = "fasttaskapi"
        return service_def

    def _get_type(self, schema: Dict[str, Any]) -> Union[str, List[ParameterType]]:
        """Extract parameter type(s) from a schema with FastTaskAPI-specific handling."""
        schema = self._resolve(schema)
        if not schema:
            return "object"

        if schema.get('type') == 'string' and schema.get('format') in {'binary', 'byte'}:
            return ['file', 'string', 'bytes']

        title = (schema.get('title') or '').lower()
        if any(key in title for key in ['imagefilemodel', 'videofilemodel', 'audiofilemodel']):
            media_type = title.replace('filemodel', '')
            return [media_type, 'file', 'string', 'bytes']

        if 'filemodel' in title or (
            schema.get('properties') and {'file_name', 'content_type'}.issubset(schema['properties'])
        ):
            return ['file', 'string', 'bytes']

        return super()._get_type(schema) 