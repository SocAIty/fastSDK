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

        # specific file models
        supported_media_types = set()
        for key in ['imagefilemodel', 'videofilemodel', 'audiofilemodel']:
            if key in title:
                media_type = title.replace('filemodel', '')
                supported_media_types.add(media_type)
 
        if len(supported_media_types) > 0:
            supported_media_types.add('file')
            supported_media_types.add('string')
            supported_media_types.add('bytes')
            return list(supported_media_types)

        # general file model
        if 'filemodel' in title or (
            schema.get('properties') and {'file_name', 'content_type'}.issubset(schema['properties'])
        ):
            return ['file', 'string', 'bytes']

        return super()._get_type(schema)
