from typing import Dict, Union, Any
from pathlib import Path
import json

from typing import TYPE_CHECKING

from fastsdk.service_specification_loader.openapi_discovery import load_openapi_from_url

if TYPE_CHECKING:
    from fastsdk.service_interaction.api_seex import APISeex


def _load_from_url_with_fallback(url: str, timeout: float = 8.0) -> Dict[str, Any]:
    """Load an OpenAPI document from a spec URL, docs page, or API root."""
    return load_openapi_from_url(url, timeout=timeout)


def _load_from_file(file_path: str) -> Dict[str, Any]:
    """Load OpenAPI spec from file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Specification file not found: {file_path}")

    with open(path, "r") as f:
        return json.load(f)


def _load_from_runpod_serverless_server(url: str, api_key: str = None, return_api_job: bool = False) -> Union[Dict[str, Any], "APISeex"]:
    """Load OpenAPI spec from RunPod serverless server."""
    from fastsdk.service_specification_loader.runpod_open_api_loader import RunpodOpenAPILoader
    loader = RunpodOpenAPILoader(url, api_key)
    if return_api_job:
        return loader.load_openapi_spec_async()
    return loader.load_openapi_spec()
