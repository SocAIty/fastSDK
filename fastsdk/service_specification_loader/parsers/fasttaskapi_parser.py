from typing import Dict, Any, Optional

from fastsdk.service_specification_loader.parsers.openapi_parser import OpenAPIParser
from fastsdk.service_definition import ParameterDefinition


class FastTaskAPIParser(OpenAPIParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.specification = "fasttaskapi"

    def _resolve_type_format(self, schema: Optional[Dict[str, Any]]) -> ParameterDefinition:
        """Override to add FastTaskAPI-specific type/format mappings."""
        schema = self._resolve(schema) or {}

        title = (schema.get('title') or '').lower()

        # Add support for Media-Toolkit MediaFiles.
        # specific media file models
        for key, fmt in [('imagefilemodel', 'image'), ('videofilemodel', 'video'), ('audiofilemodel', 'audio')]:
            if key in title:
                return ParameterDefinition(type='string', format=fmt)

        # general file model
        if 'filemodel' in title or (
            schema.get('properties') and {'file_name', 'content_type'}.issubset(schema['properties'])
        ):
            return ParameterDefinition(type='string', format='file')

        return super()._resolve_type_format(schema)
