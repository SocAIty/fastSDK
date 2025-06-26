from typing import Dict, Any, Optional, List, Union
from fastsdk.service_management.service_definition import (
    EndpointParameter, ParameterType, ServiceDefinition
)
from fastsdk.service_management.parsers.factory import create_endpoint_parameter


class BaseParser:
    """Base parser class that provides common functionality for all parsers."""
    
    def __init__(self, spec: Dict[str, Any]):
        self.spec = spec
        self._schemas = self.spec.get('components', {}).get('schemas', {})

    def _resolve(self, obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Resolve a schema reference to its actual definition."""
        if not obj:
            return None
        if "$ref" in obj:
            ref = obj["$ref"].split("/")[-1]
            return self._schemas.get(ref)
        return obj

    def _get_type(self, schema: Optional[Dict[str, Any]]) -> Union[str, List[ParameterType]]:
        """Extract parameter type(s) from a schema."""
        schema = self._resolve(schema)
        if not schema:
            return "object"

        if "type" in schema:
            if schema["type"] == "array":
                item_type = self._get_type(schema.get("items"))
                return ["array", item_type] if isinstance(item_type, str) else ["array", *item_type]
            return schema["type"]

        if "anyOf" in schema:
            types = [self._get_type(s) for s in schema["anyOf"]]
            flat = [t for typ in types for t in (typ if isinstance(typ, list) else [typ])]
            return list(flat) if len(flat) > 1 else flat.pop()

        if "allOf" in schema:
            types = [self._get_type(s) for s in schema["allOf"]]
            flat = [t for typ in types for t in (typ if isinstance(typ, list) else [typ])]
            return list(flat) if len(flat) > 1 else flat.pop()

        if "oneOf" in schema:
            types = [self._get_type(s) for s in schema["oneOf"]]
            flat = [t for typ in types for t in (typ if isinstance(typ, list) else [typ])]
            return list(flat) if len(flat) > 1 else flat.pop()

        return "object"

    def _make_param(
        self,
        name: str,
        schema: Optional[Dict[str, Any]],
        location: str,
        required: bool = False,
        description: Optional[str] = None,
    ) -> EndpointParameter:
        """Create an EndpointParameter from schema information."""
        resolved = self._resolve(schema)

        # deduplicate param types
        param_type = self._get_type(resolved)
        if isinstance(param_type, list):
            param_type = list(set(param_type))

        return create_endpoint_parameter(
            name=name,
            type=param_type,
            location=location,
            required=required,
            description=description or resolved.get("description") if resolved else None,
            param_schema=resolved,
            default=resolved.get("default") if resolved else None,
        )

    def parse_parameters(self, endpoint: Dict[str, Any]) -> List[EndpointParameter]:
        """Parse OpenAPI parameters from an endpoint definition."""
        params = []
        for param in endpoint.get("parameters", []):
            resolved = self._resolve(param)
            params.append(self._make_param(
                name=resolved["name"],
                schema=resolved.get("schema"),
                location=resolved.get("in", "query"),
                required=resolved.get("required", False),
                description=resolved.get("description"),
            ))
        return params

    def parse_body_params(self, endpoint: Dict[str, Any], path: Optional[str] = None) -> List[EndpointParameter]:
        """Parse request body parameters from an endpoint definition."""
        body = endpoint.get("requestBody", {})
        content = body.get("content", {})
        for mime_type in ["application/json", "multipart/form-data"]:
            if mime_type in content:
                schema = self._resolve(content[mime_type].get("schema"))
                if schema and schema.get("type") == "object":
                    required = schema.get("required", [])
                    return [
                        self._make_param(
                            name=prop,
                            schema=schema["properties"][prop],
                            location="body",
                            required=prop in required
                        )
                        for prop in schema.get("properties", {})
                    ]
                else:
                    return [self._make_param(
                        name=schema.get("title", "body"),
                        schema=schema,
                        location="body",
                        required=body.get("required", False),
                        description=schema.get("description"),
                    )]
        return []

    def parse(self) -> ServiceDefinition:
        """Parse the specification into a ServiceDefinition. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement the parse method") 