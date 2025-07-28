from pathlib import Path
import os
from typing import Dict, List, Optional, Any, Union, Set

from jinja2 import Environment, FileSystemLoader, Template

from fastsdk.service_definition import (
    ServiceDefinition, EndpointDefinition, EndpointParameter
)
from fastsdk.utils import normalize_name_for_py

# Constants for improved maintainability
MEDIA_TYPES = {
    "image": "ImageFile",
    "video": "VideoFile",
    "audio": "AudioFile",
    "file": "MediaFile",
}

STANDARD_TYPE_MAPPING = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "object": "Dict[str, Any]",
    "array": "List[Any]",
}

ALLOWED_PARAM_LOCATIONS = ["body", "query"]
DEFAULT_TEMPLATE_NAME = 'sdk_template.j2'


def _get_template(custom_template_path: Optional[str] = None) -> Template:
    """
    Load and return the Jinja2 template for client generation.
    
    Args:
        custom_template_path: Optional path to a custom template file
    
    Returns:
        Jinja2 Template object
    """
    if custom_template_path:
        template_path = Path(custom_template_path)
        template_dir = template_path.parent
        template_file = template_path.name
        env = Environment(loader=FileSystemLoader(template_dir))
        return env.get_template(template_file)
    
    # Use default template
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(template_dir))
    return env.get_template(DEFAULT_TEMPLATE_NAME)


def _get_type_hint(param: EndpointParameter) -> str:
    """
    Get the Python type hint for a parameter based on its type.
    
    Args:
        param: The parameter definition
        
    Returns:
        Python type hint as a string
    """
    # Handle arrays and lists
    param_types = param.type if isinstance(param.type, list) else [param.type]
    
    # For multiple types, create a Union
    includes_media = False
    mapped_types = []
    
    for p_type in param_types:
        # First check if it's a media type
        mapped_type = MEDIA_TYPES.get(p_type)
        if mapped_type:
            includes_media = True
            if mapped_type not in mapped_types:
                mapped_types.append(mapped_type)
            continue
            
        # Then check standard types
        mapped_type = STANDARD_TYPE_MAPPING.get(p_type, "Any")
        if mapped_type not in mapped_types:
            mapped_types.append(mapped_type)
    
    # Add string and bytes types when media types are included
    if includes_media:
        for extra_type in ["str", "bytes"]:
            if extra_type not in mapped_types:
                mapped_types.append(extra_type)

    # If we have multiple types, create a Union
    if len(mapped_types) > 1:
        return f"Union[{', '.join(mapped_types)}]"
    
    # Default to the first type if all mappings are the same
    return mapped_types[0]


def _format_default_value(param: EndpointParameter) -> Optional[str]:
    """
    Format the default value for a parameter based on its type.
    
    Args:
        param: The parameter definition
        
    Returns:
        The formatted default value or None if no default
    """
    if param.default is None:
        return None
    
    param_types = param.type if isinstance(param.type, list) else [param.type]
    
    # Try to find the most appropriate type for the default value
    for p_type in param_types:
        if p_type == "string":
            # Use repr() to safely escape the string for Python literals
            return repr(str(param.default))
        elif p_type == "boolean":
            # Use Python's True/False for boolean values
            if isinstance(param.default, bool):
                return str(param.default)
            elif str(param.default).lower() in ["true", "1", "yes"]:
                return "True"
            elif str(param.default).lower() in ["false", "0", "no"]:
                return "False"
        elif p_type == "integer":
            try:
                return str(int(param.default))
            except (ValueError, TypeError):
                continue
        elif p_type == "number":
            try:
                return str(float(param.default))
            except (ValueError, TypeError):
                continue
        elif p_type == "array":
            if isinstance(param.default, (list, tuple)):
                return repr(param.default)
        elif p_type == "object":
            if isinstance(param.default, dict):
                return repr(param.default)
    
    # If no type matched or conversion failed, return as safely escaped string
    return repr(str(param.default))


def _safe_escape_description(description: Optional[str]) -> Optional[str]:
    """
    Safely escape a description string for use in Python docstrings.
    
    Args:
        description: The description string to escape
        
    Returns:
        The safely escaped description or None if input is None
    """
    if not description:
        return description
    
    # Only escape triple quotes to prevent docstring termination
    escaped = description.replace('"""', '\\"\\"\\"')
    escaped = escaped.replace("'''", "\\'\\'\\'")
    
    return escaped


def _prepare_endpoint_data(endpoint: EndpointDefinition, specification: str = None) -> Optional[Dict[str, Any]]:
    """
    Prepare data for an endpoint template.
    
    Args:
        endpoint: The endpoint definition
        specification: The service specification (for path mapping)
        
    Returns:
        A dictionary with processed endpoint data or None if endpoint should be skipped
    """
    # Process parameters
    parameters = []
    for param in endpoint.parameters:
        if param.location not in ALLOWED_PARAM_LOCATIONS:
            continue
            
        default_value = _format_default_value(param)
        
        # A parameter is optional if:
        # 1. It's not required in the API definition, AND
        # 2. It doesn't have a default value already specified
        is_optional = not param.required and default_value is None
        
        # Safely escape the parameter description
        safe_description = _safe_escape_description(param.description)
        
        parameters.append({
            "name": normalize_name_for_py(param.name, lower_case=False),
            "type_hint": _get_type_hint(param),
            "default_value": default_value,
            "required": param.required,
            "optional": is_optional,
            "description": safe_description
        })

    # Sort parameters:
    # 1. Required parameters first
    # 2. Optional parameters with default values next
    # 3. Optional parameters without default values last
    parameters.sort(key=lambda x: (not x["required"], x["optional"]))

    # Handle path mapping for replicate models - use original path for request, mapped path for method name
    request_path = endpoint.path
    method_path = endpoint.path
    
    # Get return type from 200 response if available
    returns = None
    response_200 = endpoint.responses.get("200", {})
    json_schema = response_200.get("content", {}).get("application/json", {}).get("schema", {})
    if json_schema.get("type") == "object" and "properties" in json_schema:
        returns = "Dict[str, Any]"

    # Format description with proper indentation and escaping
    description = endpoint.description
    description_contains_args = False
    if description:
        # First escape the description safely
        safe_description = _safe_escape_description(description)
        # Then format with proper indentation
        description = "\n        ".join(line for line in safe_description.split("\n"))
        description_contains_args = "Args:" in description or ":param" in description

    return {
        "path": request_path,  # Original path for API requests
        "method_name": normalize_name_for_py(method_path),  # Mapped path for method name
        "description": description,
        "description_contains_args": description_contains_args,
        "parameters": parameters,
        "returns": returns,
        "raises": "ValueError: If the API request fails"
    }

        
def _detect_required_imports(endpoints_data: List[Dict[str, Any]]) -> tuple[Set[str], Set[str]]:
    """
    Analyze endpoint data to detect required imports.
    
    Args:
        endpoints_data: List of processed endpoint data
        
    Returns:
        Tuple containing (typing_imports, media_types)
    """
    media_types = set()
    typing_imports = set()

    # Type hint patterns to look for
    type_patterns = {
        "Union[": "Union",
        "List[": "List",
        "Dict[": "Dict",
        "Any": "Any",
        "Optional[": "Optional"
    }
    
    # Always include Optional for non-required parameters without defaults
    has_optional_params = any(
        any(param.get("optional", False) for param in endpoint.get("parameters", []))
        for endpoint in endpoints_data
    )
    if has_optional_params:
        typing_imports.add("Optional")
    
    # Media type patterns to look for
    media_patterns = ["ImageFile", "VideoFile", "AudioFile", "MediaFile", "MediaList"]
    
    for endpoint_data in endpoints_data:
        for param in endpoint_data.get("parameters", []):
            type_hint = param.get("type_hint", "")
            
            # Check for typing imports
            for pattern, import_name in type_patterns.items():
                if pattern in type_hint:
                    typing_imports.add(import_name)
            
            # Check for media types
            for media_type in media_patterns:
                if media_type in type_hint:
                    media_types.add(media_type)
    
    return typing_imports, media_types


def _get_file_path(save_path: Union[str, Path], class_name: str) -> Path:
    """
    Determine the file path for saving the generated client.
    
    Args:
        save_path: Directory or file path
        class_name: Name of the generated class
        
    Returns:
        Path object for the file
    """
    if not save_path:
        save_path = os.getcwd()
    save_path = Path(save_path)
    
    # Determine if save_path is a file path or directory path
    if save_path.suffix == '.py':
        file_path = save_path
        # Ensure parent directory exists
        os.makedirs(file_path.parent, exist_ok=True)
    else:
        # It's a directory path
        os.makedirs(save_path, exist_ok=True)
        file_path = save_path / f"{class_name.lower()}.py"
    
    return file_path

                
def create_sdk(
    service_definition: ServiceDefinition,
    save_path: Optional[str] = None,
    class_name: Optional[str] = None,
    template: Optional[str] = None
) -> tuple[str, str, ServiceDefinition]:
    """
    Creates a .py file for a given service definition in the given save_path.
    
    Args:
        service_definition: the service_definition including all the endpoints and models.
        save_path: Path where to save the generated file(s). Can be either:
            - A directory path: File will be saved as {class_name.lower()}.py + {class_name.lower()}.json in this directory
            - A file path: File will be saved with this exact path
            Defaults to current directory.
        class_name: Name for the generated class. Defaults to the service name.
        template: Optional path to a custom template file
        
    Returns:
        Tuple containing:
            - Path to the generated Python file
            - Name of the generated class (needed for import)
            - ServiceDefinition object of the created service (if you want use the service with the ServiceManager)
        
    Raises:
        ValueError: If service_definition is not valid
        FileNotFoundError: If template path is invalid
        IOError: If file cannot be written
    """
    # Get service definition
    if not isinstance(service_definition, ServiceDefinition):
        raise ValueError("service_definition must be a ServiceDefinition object. Load it with FastSDK().load_service_definition() first.")

    # Determine class name if not provided
    if not class_name:
        class_name = normalize_name_for_py(service_definition.display_name)

    # Get file path
    file_path = _get_file_path(save_path, class_name)
    
    # Prepare endpoint data
    endpoints_data = []
    for endpoint in service_definition.endpoints:
        endpoint_data = _prepare_endpoint_data(endpoint, service_definition.specification)
        if endpoint_data:
            endpoints_data.append(endpoint_data)
    
    # Detect required imports
    typing_imports, media_types = _detect_required_imports(endpoints_data)
    
    # Prepare template data
    template_data = {
        "class_name": class_name,
        "service": {
            "id": service_definition.id,
            "display_name": service_definition.display_name,
            "description": service_definition.description,
            "short_desc": service_definition.short_desc,
        },
        "service_id": service_definition.id,
        "endpoints": endpoints_data,
        "imports_typing": ", ".join(typing_imports) if typing_imports else None,
        "imports_media_toolkit": ", ".join(media_types) if media_types else None
    }
    
    try:
        # Get the template
        jinja_template = _get_template(template)
        
        # Render the template
        rendered = jinja_template.render(**template_data)
        
        # Save the rendered file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(rendered)

        return str(file_path), class_name, service_definition
    except FileNotFoundError:
        raise FileNotFoundError(f"Template file not found: {template}")
    except IOError as e:
        raise IOError(f"Failed to write file {file_path}: {str(e)}")
