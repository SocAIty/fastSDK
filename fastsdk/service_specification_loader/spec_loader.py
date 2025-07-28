from typing import Dict, Union, Any
from pathlib import Path
import json
import httpx
from httpx import TimeoutException, HTTPError
from fastsdk.service_definition import ServiceDefinition

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fastsdk.service_interaction import APISeex


def load_spec(spec_source: Union[str, Path, Dict[str, Any]], timeout: float = 30.0, api_key: str = None) -> Dict[str, Any]:
    """
    Load a openapi specification or service_definition from a dict, file path, or URL (with fallback locations for openapi.json).
    Args:
        spec_source: dict, file path, or URL
        timeout: Timeout for HTTP requests
    Returns:
        dict representing the specification
    Raises:
        ValueError, FileNotFoundError, HTTPError
    """

    if isinstance(spec_source, ServiceDefinition):
        return spec_source

    if isinstance(spec_source, dict):
        return spec_source

    if isinstance(spec_source, (str, Path)):
        spec_str = str(spec_source)
        if spec_str.startswith(('http://', 'https://')):
            if "runpod.ai" in spec_str:
                return _load_from_runpod_serverless_server(spec_str, api_key, return_api_job=False)
            else:
                return _load_from_url_with_fallback(spec_str, timeout)
        
        return _load_from_file(spec_str)
    raise ValueError(f"Unsupported spec source type: {type(spec_source)}")


def _download_json(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Download a JSON file from a URL."""
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _load_from_url_with_fallback(url: str, timeout: float) -> Dict[str, Any]:
    """Load OpenAPI spec from URL with automatic path resolution and fallback."""
    # Try direct URL first
    try:
        return _download_json(url, timeout)
    except (HTTPError, TimeoutException, json.JSONDecodeError):
        pass
    # Try fallback locations if not already openapi.json
    if not url.rstrip('/').endswith('openapi.json'):
        base_url = url.rstrip('/')
        possible_paths = [
            f"{base_url}/openapi.json",
            f"{base_url}/api/openapi.json",
            f"{base_url}/docs/openapi.json",
            f"{base_url}/redoc/openapi.json"
        ]
        for path in possible_paths:
            try:
                return _download_json(path, timeout)
            except (HTTPError, TimeoutException, json.JSONDecodeError):
                continue
    raise ValueError(f"Could not load spec from URL or fallback locations: {url}")


def _load_from_file(file_path: str) -> Dict[str, Any]:
    """Load OpenAPI spec from file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Specification file not found: {file_path}")
    
    with open(path, 'r') as f:
        return json.load(f)


def _load_from_runpod_serverless_server(url: str, api_key: str = None, return_api_job: bool = False) -> Union[Dict[str, Any], 'APISeex']:
    """Load OpenAPI spec from RunPod serverless server."""
    from fastsdk.service_specification_loader.runpod_open_api_loader import RunpodOpenAPILoader
    loader = RunpodOpenAPILoader(url, api_key)
    if return_api_job:
        return loader.load_openapi_spec_async()
    else:
        return loader.load_openapi_spec()
