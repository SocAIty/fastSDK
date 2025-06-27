from typing import Dict, Any, List, Union

from fastsdk.service_management.parsers.openapi_parser import OpenAPIParser
from fastsdk.service_management.service_definition import ParameterType


class FastTaskAPIParser(OpenAPIParser):
    def _get_type(self, schema: Dict[str, Any]) -> Union[str, List[ParameterType]]:
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
