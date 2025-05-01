from typing import Dict, Union, Any
from pathlib import Path
import json
import httpx
from httpx import TimeoutException, HTTPError


def load_spec(spec_source: Union[str, Path, Dict[str, Any]], timeout: float = 30.0) -> Dict[str, Any]:
    """
    Load an OpenAPI specification from various sources.
    
    Args:
        spec_source: Can be:
            - Path to OpenAPI JSON file
            - URL to OpenAPI JSON file
            - Loaded JSON dictionary
        timeout: Timeout in seconds for HTTP requests
        
    Returns:
        Loaded specification as a dictionary
        
    Raises:
        ValueError: If the source type is unsupported
        FileNotFoundError: If the spec file cannot be found
        HTTPError: If there's an error fetching the spec from a URL
    """
    if isinstance(spec_source, dict):
        return spec_source
    
    if isinstance(spec_source, (str, Path)):
        spec_str = str(spec_source)
        
        # Handle URLs
        if spec_str.startswith(('http://', 'https://')):
            return _load_from_url(spec_str, timeout)
        
        # Handle file paths
        return _load_from_file(spec_str)
    
    raise ValueError(f"Unsupported spec source type: {type(spec_source)}")


def _load_from_url(url: str, timeout: float) -> Dict[str, Any]:
    """Load OpenAPI spec from URL with automatic path resolution."""
    # If URL doesn't end with openapi.json, try to resolve it
    if not url.endswith('openapi.json'):
        base_url = url.rstrip('/')
        possible_paths = [
            f"{base_url}/openapi.json",
            f"{base_url}/api/openapi.json",
            f"{base_url}/docs/openapi.json",
            f"{base_url}/redoc/openapi.json"
        ]
        
        for path in possible_paths:
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(path)
                    response.raise_for_status()
                    return response.json()
            except (HTTPError, TimeoutException):
                continue
        
        raise ValueError(f"Could not find OpenAPI spec at any of the standard locations for URL: {url}")
    
    # Direct URL to openapi.json
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()
    

def _load_from_file(file_path: str) -> Dict[str, Any]:
    """Load OpenAPI spec from file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"OpenAPI specification file not found: {file_path}")
    
    with open(path, 'r') as f:
        return json.load(f)