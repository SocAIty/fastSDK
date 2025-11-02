from typing import Dict, Any, Optional
import hashlib
import json

from fastsdk.service_specification_loader.parsers.base_parser import BaseParser
from fastsdk.service_specification_loader.parsers.factory import (
    create_service_definition,
    create_endpoint_definition
)
from fastsdk.service_definition import (
    ServiceDefinition,
    EndpointDefinition,
    ParameterDefinition
)


class CogParser2(BaseParser):
    """Parser for new Cog format with Input/Output schemas in components."""

    def parse(self) -> ServiceDefinition:
        """Parse the new Cog specification into a ServiceDefinition."""
        info = self.spec.get('info', {})
        
        service_definition = create_service_definition(
            display_name=info.get('title'),
            description=info.get('description'),
            short_desc=info.get('summary'),
            specification="cog2",
            full_schema=self.spec,
            version=self._create_version_hash()
        )

        # Create a single predictions endpoint from Input/Output schemas
        predictions_endpoint = self._create_predictions_endpoint()
        if predictions_endpoint:
            service_definition.endpoints.append(predictions_endpoint)

        return service_definition

    def _create_predictions_endpoint(self) -> Optional[EndpointDefinition]:
        """Create the predictions endpoint from Input schema."""
        input_schema = self._schemas.get('Input')
        output_schema = self._schemas.get('Output')
        
        if not input_schema:
            return None

        endpoint = create_endpoint_definition(
            id="predictions",
            path="/predictions",
            description="",
            method="post"
        )

        # Parse parameters from Input schema
        if input_schema.get("type") == "object":
            required = input_schema.get("required", [])
            properties = input_schema.get("properties", {})
            
            for prop_name, prop_schema in properties.items():
                param = self._make_param(
                    name=prop_name,
                    schema=prop_schema,
                    location="body",
                    required=prop_name in required,
                    description=prop_schema.get("description") or prop_name
                )

                # This is a bug fix for replicate, because they require seed but don't set it in the schema.
                if param.name == "seed" and param.default is None:
                    param.default = 42

                endpoint.parameters.append(param)

        # Add response information from Output schema
        if output_schema:
            endpoint.responses = {
                "200": {
                    "description": "Successful prediction",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Output"}
                        }
                    }
                }
            }

        return endpoint

    def _resolve_type_format(self, schema: Optional[Dict[str, Any]]) -> ParameterDefinition:
        """Override to add Cog-specific type/format mappings."""
        schema = self._resolve(schema) or {}

        if schema.get("type") == "string" and schema.get("format") == "uri":
            return ParameterDefinition(type="string", format="file")

        if schema.get("type") == "file":
            return ParameterDefinition(type="string", format="file")

        return super()._resolve_type_format(schema)

    def _create_version_hash(self) -> str:
        """Create a version hash from the specification."""
        return hashlib.sha1(json.dumps(self.spec, sort_keys=True).encode()).hexdigest()
