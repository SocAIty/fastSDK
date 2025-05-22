from typing import Union, Dict, Any
from pathlib import Path
from fastsdk.service_management.parsers.open_api_parser import OpenAPIParser
from fastsdk.service_management.parsers.spec_loader import load_spec
from fastsdk.service_management.service_definition import ServiceDefinition


def parse_service_definition(spec_source: Union[str, Path, Dict[str, Any], ServiceDefinition]) -> ServiceDefinition:
    """
    Parse any supported source (dict, file path, URL) into a ServiceDefinition.
    Args:
        spec_source: dict, file path, or URL
    Returns:
        ServiceDefinition object
    Raises:
        ValueError if parsing fails
    """

    if isinstance(spec_source, ServiceDefinition):
        return spec_source

    data = load_spec(spec_source)
    try:
        return ServiceDefinition(**data)
    except Exception:
        #try:
        return OpenAPIParser(data).parse()
        #except Exception as e:
        #    raise ValueError(f"Failed to parse as ServiceDefinition or OpenAPI: {e}")
