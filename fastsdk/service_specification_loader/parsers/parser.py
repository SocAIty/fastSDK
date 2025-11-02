from typing import Union, Dict, Any
from pathlib import Path
from fastsdk.service_definition import ServiceDefinition, ServiceSpecification
from fastsdk.service_specification_loader.parsers.openapi_parser import OpenAPIParser
from fastsdk.service_specification_loader.parsers.cog.cog_parser import CogParser
from fastsdk.service_specification_loader.parsers.cog.cog_parser2 import CogParser2
from fastsdk.service_specification_loader.parsers.fasttaskapi_parser import FastTaskAPIParser

    
def _determine_specification(spec: Dict[str, Any], spec_source: Union[str, Dict[str, Any]]) -> ServiceSpecification:
    """Determine the service specification type from the OpenAPI spec."""
    info = spec.get('info', {})
    title = info.get('title', '').lower()
    desc = info.get('description', '').lower()
    combined = title + " " + desc
    schemas = spec.get('components', {}).get('schemas', {})
    
    if "fast-task-api" in info:
        return "fasttaskapi"
    if schemas:
        names = {k.lower() for k in schemas}
        if 'jobresult' in names or any(name.endswith('filemodel') for name in names):
            return "fasttaskapi"
    if title == 'cog':
        if not spec.get('paths') and 'Input' in schemas and 'Output' in schemas:
            return "cog2"
        return "cog"
    
    source_url_lower = spec_source.lower() if isinstance(spec_source, str) else ""
    if "replicate" in source_url_lower:
        return "replicate"
    if "runpod" in combined or "runpod" in source_url_lower:
        return "runpod"
    if "socaity" in combined or "api.socaity.ai" in source_url_lower:
        return "socaity"
    if "openai" in title:
        return "openai"

    return "openapi"


def _get_parser(spec: Dict[str, Any], spec_source: Union[str, Dict[str, Any]]):
    """Get the appropriate parser for the given specification."""
    specification = _determine_specification(spec, spec_source)
    
    parsers = {
        "cog": CogParser,
        "replicate": CogParser,
        "cog2": CogParser2,
        "fasttaskapi": FastTaskAPIParser,
        "runpod": OpenAPIParser,
        "socaity": FastTaskAPIParser,
        "openai": OpenAPIParser,
        "openapi": OpenAPIParser
    }
    
    parser_class = parsers.get(specification, OpenAPIParser)
    return parser_class(spec)


def parse_service_definition(loaded_spec: Union[str, Path, Dict[str, Any], ServiceDefinition], spec_source: Any = None) -> ServiceDefinition:
    """
    Parse any supported source (dict, file path, URL) into a ServiceDefinition.
    Args:
        spec_source: dict or service_definition of loaded openapi
    Returns:
        ServiceDefinition object
    Raises:
        ValueError if parsing fails
    """

    if isinstance(loaded_spec, ServiceDefinition):
        return loaded_spec

    if not hasattr(loaded_spec, "endpoints"):
        parser = _get_parser(loaded_spec, spec_source)
        return parser.parse()
        
    try:
        return ServiceDefinition(**loaded_spec)
    except Exception:
        parser = _get_parser(loaded_spec, spec_source)
        return parser.parse()
