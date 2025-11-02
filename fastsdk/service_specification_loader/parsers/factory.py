"""
Factory module for safely creating model instances with proper defaults.

This module provides factory functions for creating model instances
with appropriate fallback values for fields that might be required in practice
even if they're marked as Optional in the model definition.
"""

from typing import Optional, List, Dict, Any, Union
from fastsdk.service_definition import (
    ServiceDefinition, EndpointDefinition, EndpointParameter,
    ServiceSpecification, ParameterLocation, ParameterDefinition
)
from datetime import datetime, timezone
import uuid


def create_service_definition(
    id: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    short_desc: Optional[str] = None,
    specification: ServiceSpecification = "other",
    endpoints: List[EndpointDefinition] = None,
    used_models: Optional[List[Dict]] = None,
    category: Optional[List[str]] = None,
    family_id: Optional[str] = None,
    full_schema: Optional[Dict[str, Any]] = None,  # raw OpenAPI/Cog schema
    source_identifier: Optional[str] = None,  # Store original source (URL/path)
    version: Optional[str] = None  # should be the hash of the openapi specification
) -> ServiceDefinition:
    """Factory function to create a ServiceDefinition instance."""
    if id is None:
        id = str(uuid.uuid4())  # Generate default ID if not provided
    return ServiceDefinition(
        id=id,
        display_name=display_name or "Unnamed Service",
        description=description,
        short_desc=short_desc or description,  # Fallback short_desc to description
        specification=specification,
        endpoints=endpoints or [],
        used_models=used_models or [],
        category=category,
        family_id=family_id,
        full_schema=full_schema or {},
        source_identifier=source_identifier,
        created_at=datetime.now(timezone.utc).isoformat(),
        version=version
    )


def create_endpoint_definition(
    path: str,
    id: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    short_desc: Optional[str] = None,
    method: Optional[str] = None,  # post, get, put, delete, etc.
    parameters: List[EndpointParameter] = None,
    responses: Dict[str, Dict[str, Any]] = None,
    timeout_s: Optional[float] = None
) -> EndpointDefinition:
    """Factory function to create an EndpointDefinition instance."""
    # Use path and method for a default ID if operationId is missing
    effective_id = id or f"{method}_{path}".replace("/", "_").strip("_")
    return EndpointDefinition(
        id=effective_id,
        path=path,
        display_name=display_name or effective_id,  # Fallback display_name to id
        description=description,
        short_desc=short_desc or display_name,  # Fallback short_desc to display_name
        method=method.upper() if isinstance(method, str) else method,
        parameters=parameters or [],
        responses=responses or {},
        x_timeout_s=timeout_s
    )


def create_endpoint_parameter(
    name: str,
    definition: Union[ParameterDefinition, List[ParameterDefinition]],
    required: bool = False,
    default: Optional[Any] = None,
    location: ParameterLocation = "query",
    description: Optional[str] = None,
    param_schema: Optional[Dict[str, Any]] = None
) -> EndpointParameter:
    """Factory function to create an EndpointParameter instance."""

    valid_locations = ParameterLocation.__args__
    if location not in valid_locations:
        location = 'query' # Fallback, though ideally this shouldn't be hit.

    return EndpointParameter(
        name=name,
        definition=definition,
        required=required,
        default=default,
        location=location,
        description=description,
        param_schema=param_schema or {}
    )
