from typing import Dict, Any, Optional, List, Union
from fastsdk.service_definition import (
    EndpointParameter, ServiceDefinition, ParameterDefinition
)
from fastsdk.service_specification_loader.parsers.factory import create_endpoint_parameter


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

    def _build_param_definition(self, schema: Optional[Dict[str, Any]]) -> ParameterDefinition:
        """Build a ParameterDefinition from a resolved schema node."""
        resolved = self._resolve(schema) or {}

        p_type = resolved.get("type") or "object"
        p_format = resolved.get("format")

        # Map common cases without forcing a particular strategy; subclasses can refine
        # Keep 'binary'/'byte' as-is; specialized parsers may convert to 'file'
        # Preserve constraints and enums
        return ParameterDefinition(
            type=p_type,
            format=p_format,
            enum=resolved.get("enum"),
            minLength=resolved.get("minLength"),
            maxLength=resolved.get("maxLength"),
            minimum=resolved.get("minimum"),
            maximum=resolved.get("maximum"),
            additional_properties=resolved.get("additionalProperties")
        )
        
    def _resolve_type_format(self, schema: Optional[Dict[str, Any]]) -> ParameterDefinition:
        """Resolve type and format for a single schema node. Subclasses can override for custom logic."""
        schema = self._resolve(schema) or {}

        if schema.get("type") == "array":
            # Recursively resolve the item type/format
            item_def = self._resolve_type_format(schema.get("items"))
            # For arrays, set format to the item's type or format
            arr_format = getattr(item_def, "format", None) or getattr(item_def, "type", None)
            # Preserve constraints from the array schema itself if any
            return ParameterDefinition(
                type="array",
                format=arr_format,
                enum=None,  # Arrays don't have enum directly
                minLength=schema.get("minLength"),
                maxLength=schema.get("maxLength"),
                minimum=schema.get("minimum"),
                maximum=schema.get("maximum"),
                additional_properties=None  # Arrays don't have additional_properties
            )

        # Base case: build definition from schema
        return self._build_param_definition(schema)

    def _get_type(self, schema: Optional[Dict[str, Any]]) -> Union[ParameterDefinition, List[ParameterDefinition]]:
        """Extract ParameterDefinition(s) from a schema, honoring anyOf/allOf/oneOf."""
        schema = self._resolve(schema) or {}

        # Handle composition keywords first
        for key in ("anyOf", "allOf", "oneOf"):
            if key in schema:
                defs: List[ParameterDefinition] = []
                for sub_schema in schema[key]:
                    sub_def = self._resolve_type_format(sub_schema)
                    defs.append(sub_def)
                # Deduplicate by (type, format)
                dedup: Dict[tuple, ParameterDefinition] = {}
                for d in defs:
                    dedup[(d.type, d.format)] = d
                return list(dedup.values())

        # Simple schema: delegate to _resolve_type_format
        return self._resolve_type_format(schema)

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

        definition = self._get_type(resolved)

        return create_endpoint_parameter(
            name=name,
            definition=definition,
            location=location,
            required=required,
            description=description or (resolved.get("description") if resolved else None),
            param_schema=resolved,
            default=(resolved.get("default") if resolved else None),
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
