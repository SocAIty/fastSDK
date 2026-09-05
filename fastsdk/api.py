"""
The public, module-level API of fastsdk.

These functions wrap the FastSDK singleton so users never have to deal with it directly:

    import fastsdk

    client = fastsdk.connect("http://localhost:8009")          # use a service right now
    stub = fastsdk.generate_stub("http://localhost:8009")      # generate a client stub file
    service = fastsdk.inspect_service("replicate:owner/name")  # look at a service without side effects
    service = fastsdk.register_service("./openapi.json")       # add a service to the registry
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from socaity_schemas.platform import AIService

from fastsdk.fastSDK import FastSDK

if TYPE_CHECKING:
    from fastsdk.fastClient import FastClient
    from fastsdk.fastStub import FastStub


def connect(
    source: Union[str, Path, Dict[str, Any], AIService],
    api_key: Optional[str] = None,
    **kwargs
) -> 'FastClient':
    """
    Connect to a service and get a ready-to-use client - no code generation, no files.

    Args:
        source: Service URL ("http://localhost:8009"), openapi.json path/dict, AIService,
            Replicate model reference ("replicate:owner/name") or a registered service ID/name.
        api_key: Optional API key. Falls back to environment variables.
        **kwargs: Additional service loading arguments (see inspect_service).

    Returns:
        FastClient. Call endpoints generically via client.submit_job("/endpoint", **params).

    Example:
        client = fastsdk.connect("http://localhost:8009")
        job = client.submit_job("/text2voice", text="hello world")
        audio = job.get_result()
    """
    return FastSDK().connect(source, api_key=api_key, **kwargs)


def inspect_service(
    source: Union[str, Path, Dict[str, Any], AIService],
    api_key: Optional[str] = None,
    **kwargs
) -> AIService:
    """
    Load and parse a service into an AIService without registering it anywhere.
    Pure function: no side effects on the registry.

    Args:
        source: Service URL, openapi.json path/dict, Replicate model reference or AIService.
        api_key: Required for RunPod and Replicate sources.
        **kwargs: Overrides such as provider, service_id, name.

    Returns:
        AIService whose primary deployment carries the parsed ServiceContract
        (endpoints, parameters) and the resolved service address.
    """
    return FastSDK.inspect_service(source, api_key=api_key, **kwargs)


def generate_stub(
    source: Union[str, Path, Dict[str, Any], AIService],
    save_path: Optional[str] = None,
    class_name: Optional[str] = None,
    template: Optional[str] = None,
    **kwargs
) -> 'FastStub':
    """
    Generate a Python client stub file (.py) for a service. The generated class has one typed
    method per endpoint. The service is also registered in the registry, so the stub can be
    used immediately in the same process.

    Args:
        source: Service URL, openapi.json path/dict, AIService, Replicate model
            reference or a registered service ID/name.
        save_path: File or directory path for the generated .py file. Defaults to the current directory.
        class_name: Name of the generated class. Defaults to the (normalized) service name.
        template: Optional custom Jinja2 template path.
        **kwargs: Additional service loading arguments (e.g. api_key, service_name).

    Returns:
        FastStub with .path, .class_name, .service and .client().

    Example:
        stub = fastsdk.generate_stub("http://localhost:8009", save_path="clients/")
        client = stub.client()                     # use it right away
        # or in the next run:
        # from clients.speechcraft import SpeechCraft
    """
    return FastSDK().generate_stub(source, save_path=save_path, class_name=class_name, template=template, **kwargs)


def register_service(
    source: Union[str, Path, Dict[str, Any], AIService],
    **kwargs
) -> AIService:
    """
    Load a service and add it to the registry. Idempotent: re-registering a service with the
    same ID replaces the previous entry.

    Args:
        source: Service URL, openapi.json path/dict, Replicate model reference or AIService.
        **kwargs: Overrides such as service_name, service_id, service_address, provider, api_key, ...

    Returns:
        The registered AIService.
    """
    return FastSDK().register_service(source, **kwargs)


def get_service(service_id_or_name: str) -> Optional[AIService]:
    """Get a registered service by ID or name. Returns None if not found."""
    return FastSDK().get_service(service_id_or_name)


def list_services() -> List[AIService]:
    """List all services currently in the registry."""
    return FastSDK().service_registry.list_services()


def remove_service(service_id_or_name: str) -> bool:
    """Remove a service from the registry. Returns True if it was removed."""
    return FastSDK().service_registry.remove_service(service_id_or_name)


def submit_factory(
    path: str,
    data: dict,
    *,
    address: str,
    api_key: str = None,
    materialize_media: bool = True,
):
    """Submit a job to a gateway factory path. No catalog service required.

    Returns the same ``APISeex`` handle as ``FastClient.submit_job``.
    """
    return FastSDK().submit_factory(
        path, data, address=address, api_key=api_key, materialize_media=materialize_media
    )


def track_job(
    job_id: str,
    *,
    address: str,
    api_key: str = None,
    materialize_media: bool = True,
):
    """Re-attach to a running gateway job and poll until it is terminal."""
    return FastSDK().track_job(
        job_id, address=address, api_key=api_key, materialize_media=materialize_media
    )
