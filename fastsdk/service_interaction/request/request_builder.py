from pydantic import BaseModel
from typing import Union, Any

from fastsdk.service_management.service_definition import ParameterLocation, EndpointDefinition, ServiceAddress


class APIKeyError(Exception):
    """Custom exception for API key validation errors."""
    def __init__(self, message: str, service_name: str, signup_url: str):
        message = f"{message}\nPlease create an account at {signup_url} and get an API key. Set the API key using environment variable {service_name.upper()}_API_KEY."
        super().__init__(message)


class RequestData:
    def __init__(self, query_params: dict = {}, body_params: dict = {}, file_params: Union[dict, Any, None] = None, headers: dict = {}, url: str = ""):
        self.query_params = query_params
        self.body_params = body_params
        self.file_params = file_params
        self.headers = headers
        self.url = url


async def format_request_params(endpoint: EndpointDefinition, *args, **kwargs) -> RequestData:
    """
    Prepare all request parameters for the endpoint.
    Puts the parameters from arg and kwargs into the right location RequestData object.
    """

    named_args = {k: v for k, v in zip(endpoint.parameters, args)}
    named_args.update(kwargs)

    rq = RequestData()
    for param in endpoint.parameters:
        param_value = named_args.get(param.name, param.default)
        if param_value is None and param.required:
            raise ValueError(f"Required parameter '{param.name}' is missing")
        if param.location == ParameterLocation.query:
            rq.query_params[param.name] = param_value
        elif param.location == ParameterLocation.body:
            rq.body_params[param.name] = param_value
        elif param.location == ParameterLocation.file:
            rq.file_params[param.name] = param_value

    return rq


def _build_request_url(service_address: ServiceAddress, endpoint: EndpointDefinition, query_params: dict = None) -> str:
    """Build the complete request URL with query parameters."""
    base_url = f"{service_address.url}/{endpoint.path.lstrip('/')}"
    if query_params:
        query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
        return f"{base_url}?{query_string}"
    return base_url 