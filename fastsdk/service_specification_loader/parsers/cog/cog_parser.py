from typing import Dict, Any, List, Optional

from fastsdk.service_specification_loader.parsers.openapi_parser import OpenAPIParser
from fastsdk.service_definition import (
    EndpointParameter, ServiceDefinition, ParameterDefinition
)


class CogParser(OpenAPIParser):
    """Parser for old Cog format services that extends OpenAPI with Cog-specific schema parsing."""

    def parse(self) -> ServiceDefinition:
        """Parse the Cog specification into a ServiceDefinition."""
        service_def = super().parse()
        service_def.specification = "cog"
        return service_def

    def parse_body_params(self, endpoint: Dict[str, Any], path: Optional[str] = None) -> List[EndpointParameter]:
        """Parse body parameters with Cog-specific handling for /predictions endpoint."""
        if path != '/predictions':
            return super().parse_body_params(endpoint)

        body = endpoint.get("requestBody", {})
        content = body.get("content", {}).get("application/json", {})
        schema = self._resolve(content.get("schema"))
        if not schema:
            return []

        input_ref = schema.get("properties", {}).get("input", {}).get("$ref")
        input_schema = self._resolve({"$ref": input_ref}) if input_ref else None
        if not input_schema or input_schema.get("type") != "object":
            return []

        required = input_schema.get("required", [])
        
        params = []
        for prop in input_schema.get("properties", {}):
            param = self._make_param(
                name=prop,
                schema=input_schema["properties"][prop],
                location="body",
                required=prop in required,
                description=input_schema["properties"][prop].get("description") or prop
            )
            # This is a bug fix for replicate, because they require seed but don't set it in the schema.
            if param.name == "seed":
                param.default = 42
            params.append(param)

        return params

    def _resolve_type_format(self, schema: Optional[Dict[str, Any]]) -> ParameterDefinition:
        """Override to add Cog-specific type/format mappings."""
        schema = self._resolve(schema) or {}

        if schema.get("type") == "string" and schema.get("format") == "uri":
            return ParameterDefinition(type="string", format="file")

        if schema.get("type") == "file":
            return ParameterDefinition(type="string", format="file")

        return super()._resolve_type_format(schema)
