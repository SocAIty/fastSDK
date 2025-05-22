from typing import Dict, Any, List, Optional, Union
from fastsdk.service_management.parsers.schema_parsers.base_parser import BaseSchemaParser
from fastsdk.service_management.service_definition import EndpointParameter, ParameterType


class CogSchemaParser(BaseSchemaParser):
    def parse_body_params(self, endpoint: Dict[str, Any], path: Optional[str] = None) -> List[EndpointParameter]:
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
        return [
            self._make_param(
                name=prop,
                schema=input_schema["properties"][prop],
                location="body",
                required=prop in required,
                description=input_schema["properties"][prop].get("description") or prop
            )
            for prop in input_schema.get("properties", {})
        ]

    def _get_type(self, schema: Optional[Dict[str, Any]]) -> Union[str, List[ParameterType]]:
        schema = self._resolve(schema)
        if not schema:
            return "object"

        if schema.get("type") == "string" and schema.get("format") == "uri":
            return ["file", "string"]

        if schema.get("type") == "file":
            return ["file", "string"]

        return super()._get_type(schema)
