"""
The public, module-level API of fastsdk.

These functions wrap the FastSDK singleton so users never have to deal with it directly:

    import fastsdk

    client = fastsdk.connect("http://localhost:8009")          # use a service right now
    service = fastsdk.inspect_service("replicate:owner/name")  # look at a service without side effects
    service = fastsdk.register_service("./openapi.json")       # add a service to the registry
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from socaity_schemas.platform.catalog.service import Service

from fastsdk.fastSDK import FastSDK

if TYPE_CHECKING:
    from fastsdk.fastClient import FastClient


def connect(
    source: Union[str, Path, Dict[str, Any], Service],
    api_key: Optional[str] = None,
    **kwargs
) -> 'FastClient':
    """
    Connect to a service and get a ready-to-use client. No files written.

    Args:
        source: Service URL ("http://localhost:8009"), openapi.json path/dict, Service,
            Replicate model reference ("replicate:owner/name") or a registered service ID/name.
        api_key: Optional API key. Falls back to environment variables.
        **kwargs: Additional service loading arguments (see inspect_service).

    Returns:
        FastClient. Call endpoints via client.submit_job("/endpoint", **params).

    Example:
        client = fastsdk.connect("http://localhost:8009")
        job = client.submit_job("/text2voice", text="hello world")
        audio = job.get_result()
    """
    return FastSDK().connect(source, api_key=api_key, **kwargs)


def inspect_service(
    source: Union[str, Path, Dict[str, Any], Service],
    api_key: Optional[str] = None,
    **kwargs
) -> Service:
    """
    Load and parse a service into an Service without registering it anywhere.
    Pure function: no side effects on the registry.

    Args:
        source: Service URL, openapi.json path/dict, Replicate model reference or Service.
        api_key: Required for RunPod and Replicate sources.
        **kwargs: Overrides such as provider, service_id, name.

    Returns:
        Service whose primary details binding carries the parsed ServiceContract
        (endpoints, parameters) and the resolved service address.
    """
    return FastSDK.inspect_service(source, api_key=api_key, **kwargs)


def register_service(
    source: Union[str, Path, Dict[str, Any], Service],
    **kwargs
) -> Service:
    """
    Load a service and add it to the registry. Idempotent: re-registering a service with the
    same ID replaces the previous entry.

    Args:
        source: Service URL, openapi.json path/dict, Replicate model reference or Service.
        **kwargs: Overrides such as service_name, service_id, service_address, provider, api_key, ...

    Returns:
        The registered Service.
    """
    return FastSDK().register_service(source, **kwargs)


def get_service(service_id_or_name: str) -> Optional[Service]:
    """Get a registered service by ID or name. Returns None if not found."""
    return FastSDK().get_service(service_id_or_name)


def list_services() -> List[Service]:
    """List all services currently in the registry."""
    return FastSDK().service_registry.list_services()


def remove_service(service_id_or_name: str) -> bool:
    """Remove a service from the registry. Returns True if it was removed."""
    return FastSDK().service_registry.remove_service(service_id_or_name)
