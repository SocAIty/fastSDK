"""
Factory module for safely creating model instances with proper defaults.

This module provides factory functions for creating model instances
with appropriate fallback values for fields that might be required in practice
even if they're marked as Optional in the model definition.
"""

from typing import Optional, List, Dict, Any, Union
from fastsdk.service_management.service_definition import (
    ServiceDefinition, EndpointDefinition, EndpointParameter,
    ServiceSpecification, ParameterType, ParameterLocation
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
    used_models: Optional[List[Dict]] = None,  # Assuming models might be parsed later
    category: Optional[List[str]] = None,
    family_id: Optional[str] = None,
    schemas: Optional[Dict[str, Any]] = None,  # Store raw schemas
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
        schemas=schemas or {},
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
        method=method,
        parameters=parameters or [],
        responses=responses or {},
        timeout_s=timeout_s
    )


def create_endpoint_parameter(
    name: str,
    type: Union[ParameterType, Any] = "string",  # Default to string
    required: bool = False,
    default: Optional[Any] = None,
    location: ParameterLocation = "query",  # Default to query
    description: Optional[str] = None,
    param_schema: Optional[Dict[str, Any]] = None
) -> EndpointParameter:
    """Factory function to create an EndpointParameter instance."""
    return EndpointParameter(
        name=name,
        type=type,
        required=required,
        default=default,
        location=location,
        description=description,
        param_schema=param_schema or {}  # Ensure schema is at least an empty dict
    )
