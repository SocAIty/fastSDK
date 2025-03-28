import inspect
import threading
from typing import Tuple, Any
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel

from fastCloud import FastCloud, ReplicateUploadAPI, SocaityUploadAPI
from fastsdk.definitions.enums import EndpointSpecification
from fastsdk.utils import normalize_name
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.definitions.ai_model import AIModelDescription
from fastsdk.web.definitions.service_adress import (ServiceAddress, SocaityServiceAddress, ReplicateServiceAddress,
                                                    RunpodServiceAddress, create_service_address)
from fastsdk.web.req.endpoint_request import EndPointRequest

from fastsdk.registry import Registry
from fastsdk.web.req.request_handler import RequestHandler
from fastsdk.web.req.request_handler_replicate import RequestHandlerReplicate
from fastsdk.web.req.request_handler_runpod import RequestHandlerRunpod
from fastsdk.web.req.request_handler_socaity import RequestHandlerSocaity


class APIClient:
    """
    The APIClient is used to interact with an API (service) and its endpoints.
    A service usually has multiple endpoints with different routes.
    The APIClient makes it easy to add and call these endpoints.
    """
    def __init__(
            self,
            # required information for execution
            service_urls: dict | str | list | ServiceAddress,
            active_service: str | None = None,
            # optional information for documentation and services
            service_name: str | None = None,
            service_description: str | None = None,
            model_description: AIModelDescription | None = None,
            # optional args for s3 upload and co.
            fast_cloud: FastCloud | None = None,
            upload_to_cloud_threshold_mb: int | None = None,
            api_keys: dict[str, str] | None = None,
            *args,
            **kwargs
    ):
        """
        Initialize the APIClient with the required information.
        :param service_urls: urls to possible hosts of the service api. Structured as { service_url_nickname: url }
        :param active_service: which of the services to use
        :param service_name: the service_name of the service. Used to find the service in the registry.
        :param service_description: a description of the service.
        :param model_description: a description of the model_description used in the service. Used for documentation.
        :param fast_cloud: if specified, files will be uploaded via fastcloud for file transfer.
             Then a file_url is sent to the endpoint instead of the file as bytes.
             Property can be overwritten with the fast_sdk init of the service.
        :param upload_to_cloud_threshold_mb:
            if the combined file size is greater than this limit, the file is uploaded to the cloud handler.
        :param api_keys: dictionary structured as {service_url_nickname: api_key} to add api keys to the service.
        """
        # create the service urls
        self.service_urls = self._create_service_urls(service_urls)

        # Default active service
        self._default_service = active_service or next(iter(self.service_urls))

        # service metadata
        if service_name:
            normalized_name = normalize_name(service_name)
            self.service_name = normalized_name if normalized_name is not None else self.service_urls.get(self._default_service)
        else:
            self.service_name = self.service_urls.get(self._default_service)
        self.service_description = service_description
        self.model_description = model_description

        # endpoint function holders
        self.endpoint_request_funcs = {}  # { endpoint_name: function, endpoint_name_async: function }
        self.endpoints = {}  # { endpoint_name: endpoint }

        # add api keys for authorization
        # If nothing is specified we use the default api keys defined by environment variables
        if api_keys is None:
            from fastsdk.settings import API_KEYS
            # Filter out None values and ensure all keys and values are strings
            self.api_keys = {str(name): str(val) for name, val in API_KEYS.items() if val is not None}
        elif isinstance(api_keys, str):
            self.api_keys = {str(active_service): str(api_keys)}
        else:
            # Ensure all keys and values are strings
            self.api_keys = {str(name): str(val) for name, val in api_keys.items() if val is not None}

        # request handlers are shared between active services.
        # They get lazy initialized when a request is made to a not yet initialized service.
        self.request_handlers = {}
        self.upload_to_cloud_threshold_mb = upload_to_cloud_threshold_mb
        self.fast_cloud = fast_cloud

        # init request handlers and their configurations
        # We use a thread-local storage for the request handlers to avoid conflicts between threads.
        # Store service configurations
        # Note that each value in the thread local only exists in the specific thread.
        # Initialize thread-local storage
        self._thread_local = threading.local()
        self._thread_local.current_service = self._default_service

        # add the service client to the registry. This makes it easier to find them later on.
        # Is also used in other packages.
        Registry().add_service(self.service_name, self)

    @property
    def active_service(self) -> str:
        """
        Get the active service for the current thread.
        :return: Active service name
        """
        if not hasattr(self._thread_local, 'current_service'):
            self.active_service = self._default_service

        return self._thread_local.current_service

    @active_service.setter
    def active_service(self, service_name: str):
        """
        Set the active service for the upcoming requests in the current thread context.

        :param service_name: Name of the service to switch to
        :raises ValueError: If the service service_name is not found in service configurations
        """
        if service_name not in self.service_urls:
            raise ValueError(f"Service {service_name} not found in service URLs")

        # Set the current service for this thread
        self._thread_local.current_service = service_name

    def _get_current_request_handler(self) -> RequestHandler:
        """
        Get or create a request handler for the current thread's active service.

        :return: RequestHandler for the current service
        """
        current_service = self.active_service
        # Lazy initialize request handler
        if current_service not in self.request_handlers:
            service_address = self.service_urls.get(current_service)
            if service_address is None:
                raise ValueError(f"Service {current_service} not found in service URLs")

            # Create request handler
            self.request_handlers[current_service] = create_request_handler(
                service_address=service_address,
                api_key=self.api_keys.get(current_service),
                fast_cloud=self.fast_cloud,
                upload_to_cloud_threshold_mb=self.upload_to_cloud_threshold_mb
            )

        return self.request_handlers[current_service]

    def add_service_url(self, service_name: str, service_url: str):
        self.service_urls[service_name] = create_service_address(service_url)

    def add_api_key(self, service_name: str | None, key: str | None):
        """
        Add or update an API key for a service.
        If a request handler for the service exists, it will be recreated to use the new API key.
        :param service_name: Service service_name or nickname
        :param key: API key to add
        :return: Updated API keys dictionary
        """
        if not key:
            return self.api_keys

        if not service_name:
            service_name = self.active_service

        self.api_keys[service_name] = key

        if service_name in self.request_handlers:
            # force creating a new one. Note: If there's references to it, it won't be deleted.
            # chose this implementation instead of del to avoid requests going into empty.
            # However, this might lead to memory leaks.
            self.request_handlers[service_name] = None

        return self.api_keys

    def set_fast_cloud(
            self,
            fast_cloud: FastCloud,
            upload_to_cloud_threshold_mb: float | None = 3,
            max_upload_file_size_mb: float | None = 1000
    ):
        """
        Set or update the cloud storage handler for all request_handlers.

        :param fast_cloud: Cloud storage handler to use
        :param upload_to_cloud_threshold_mb: Threshold for cloud upload in MB
        :return: Self, for method chaining
        """
        # Set thread-local cloud storage
        self.fast_cloud = fast_cloud

        if upload_to_cloud_threshold_mb is None:
            upload_to_cloud_threshold_mb = 3
        self.upload_to_cloud_threshold_mb = float(upload_to_cloud_threshold_mb)

        for service_name, handler in self.request_handlers.items():
            handler.set_fast_cloud(fast_cloud,
                                   upload_to_cloud_threshold_mb=upload_to_cloud_threshold_mb,
                                   max_upload_file_size_mb=max_upload_file_size_mb)

        return self

    def _create_endpoint_func(
            self,
            endpoint: EndPoint,
            is_async: bool = False,
            retries_on_error: int = 3
    ):
        """
        Creates a new function to call an endpoint and adds it to the class.
        :param endpoint: the definition of the endpoint
        :param is_async: if the endpoint is called async_jobs or sync
        :return: the wrapped function
        """
        def endpoint_job_wrapper(*args, **kwargs) -> EndPointRequest:
            """
            This function is called when the endpoint is called.
            It submits a request to the given endpoint and receives an AsyncJob from the request handler.
            It determines what kind of response is coming back and if it was a socaity service.
            If it was a socaity service, it returns a SocaityRequest object.
            The socaity request object, refreshes itself until the final server_response is retrieved.
            :param args:
            :param kwargs:
            :return:
            """
            # Get the current service's request handler
            request_handler = self._get_current_request_handler()

            endpoint_request = EndPointRequest(
                endpoint=endpoint,
                request_handler=request_handler,
                retries_on_error=retries_on_error
            )
            endpoint_request.request(*args, **kwargs)
            if not is_async:
                endpoint_request.wait_until_finished()

            return endpoint_request

        # create method parameters
        ep_args = endpoint.get_parameter_definition_as_dict()
        func_name = f"{endpoint.endpoint_route}" if not is_async else f"{endpoint.endpoint_route}_async"
        endpoint_job_wrapper.__name__ = func_name
        sig_params = [
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ptype)
            for name, ptype in ep_args.items()
        ]
        endpoint_job_wrapper.__signature__ = inspect.Signature(parameters=sig_params)
        self.__setattr__(func_name, endpoint_job_wrapper)
        self.endpoint_request_funcs[func_name] = endpoint_job_wrapper

        return endpoint_job_wrapper

    def _add_endpoint(self, endpoint: EndPoint) -> Tuple[callable, callable]:
        """
        Adds and endpoint and convenience functions to an service
        You can call the APIClient.endpoint_function_name to send a request to the endpoint and wait for the server_response.
        Use the APIClient.endpoint_function_name_async to send a request and get an asyncio_task object.
        --> this is in particular useful to get fine graded updates of the server.
        :param endpoint: an instance of an EndPoint object.
        :return: a tuple of the sync and async_jobs function
        """
        # add the sync coro
        sync_func = self._create_endpoint_func(endpoint, is_async=False)
        async_func = self._create_endpoint_func(endpoint, is_async=True)

        self.endpoints[endpoint.endpoint_route] = endpoint

        return sync_func, async_func

    def add_endpoint(
            self,
            endpoint_route: str,
            query_params: dict[str, Any] | BaseModel | None = None,
            body_params: dict[str, Any] | BaseModel | None = None,
            file_params: dict[str, Any] | None = None,
            timeout: int = 3600,
            refresh_interval_s: float = 0.5,
            normalize_route_name: bool = True
    ):
        """
        :param endpoint_route: for example api/img2img/stable_diffusion
        :param query_params: Defines the parameters which are send as url?params=... to the endpoint.
            It is a dict in format {param_name: param_type} for example {"my_text": str}.
        :param body_params: Defines the parameters which are send in the request body e.g. post.
            Expects a dict in format {param_name: param_type} for example {"my_text": str}
        :param file_params: Defines the parameters which are send as files. Might be, read, converted, uploaded.
        :param timeout: time in seconds until the request to the endpoint fails.
        :param refresh_interval_s: in which interval in seconds is the status checkpoint called.
        :param normalize_route_name:
            If on, removes special characters and replaces spaces and under-score with hyphens.
            This is used to standardize endpoint names across the socaity services.
            turn off, when you are 100% sure about the endpoint path.
            For example when you work with any other arbitrary service.
        """
        if normalize_route_name:
            endpoint_route = normalize_name(endpoint_route, preserve_paths=True)
            endpoint_route = endpoint_route.strip("/")
        if endpoint_route in ["health", "status", "cancel"]:
            print(f"Endpoint name {endpoint_route} is reserved and can't be used. We ignore it")
            return

        if endpoint_route in self.endpoint_request_funcs:
            raise ValueError(f"Endpoint {endpoint_route} already exists in the service.")

        ep = EndPoint(
            endpoint_route=endpoint_route,
            query_params=query_params or {},
            body_params=body_params or {},
            file_params=file_params or {},
            timeout=timeout,
            refresh_interval_s=refresh_interval_s
        )
        self._add_endpoint(ep)

    def list_endpoints(self) -> dict:
        """
        List all available endpoints of the service with their parameters.
        :return: a list of endpoint names
        """
        for name, func in self.endpoint_request_funcs.items():
            print(f"{name}: {func.__signature__}")
        return self.endpoint_request_funcs

    @staticmethod
    def _create_service_urls(service_urls: dict | str | list | ServiceAddress):
        # set service urls and fix them if necessary
        if isinstance(service_urls, str):
            service_urls = {"0": create_service_address(service_urls)}
        elif isinstance(service_urls, list):
            service_urls = {str(i): create_service_address(url) for i, url in enumerate(service_urls)}
        elif isinstance(service_urls, ServiceAddress):
            service_urls = {"0": service_urls}

        # fix problems with "handwritten" urls
        service_urls = { k: create_service_address(addr) for k, addr in service_urls.items() }
        return service_urls

    def __call__(self, endpoint_route: str, call_async: bool = False, *args, **kwargs) -> EndPointRequest:
        """
        Call an endpoint using the current thread's active service context.

        :param endpoint_route: The endpoint route to call
        :param call_async: Whether to call the endpoint asynchronously
        :param args: Positional arguments for the endpoint
        :param kwargs: Keyword arguments for the endpoint
        :return: EndPointRequest object
        """
        # Get the endpoint
        normalized_route = normalize_name(endpoint_route, preserve_paths=True)
        if normalized_route is None:
            raise ValueError(f"Invalid endpoint route: {endpoint_route}")
        endpoint_route = normalized_route.strip("/")

        if call_async:
            endpoint_route = f"{endpoint_route}_async" if not endpoint_route.endswith("_async") else endpoint_route

        if endpoint_route not in self.endpoint_request_funcs:
            raise ValueError(f"Function {endpoint_route} not found in the service.")

        # Call the endpoint function
        return self.endpoint_request_funcs[endpoint_route](*args, **kwargs)

    def __del__(self):
        """
        Remove the service from the registry when the object is deleted.
        """
        try:
            Registry().remove_service(self)
        except Exception as e:
            pass


def create_request_handler(
        service_address: str | ServiceAddress | SocaityServiceAddress | RunpodServiceAddress | ReplicateServiceAddress,
        api_key: str | None = None,
        fast_cloud: FastCloud | None = None,
        upload_to_cloud_threshold_mb: float | None = None
) -> RequestHandler:
    """
    Create a request handler based on the service address.
    :param service_address: The address of the service
    :param api_key: The API key for the service
    :param fast_cloud: The cloud handler to use for file uploads.
        If not specified, the cloud handler is created based on the service type (if api-key is given).
    :param upload_to_cloud_threshold_mb: Threshold for cloud upload in MB
    """

    _rqh = RequestHandler

    if isinstance(service_address, str):
        service_address = create_service_address(service_address)

    if isinstance(service_address, ReplicateServiceAddress):
        _rqh = RequestHandlerReplicate
        if fast_cloud is None and api_key is not None:
            fast_cloud = ReplicateUploadAPI(api_key=api_key)
    elif isinstance(service_address, RunpodServiceAddress):
        _rqh = RequestHandlerRunpod
    elif isinstance(service_address, SocaityServiceAddress):
        _rqh = RequestHandlerSocaity
        upload_to_cloud_threshold_mb = 3  # 0.1 #1
        if fast_cloud is None and api_key is not None:
            # for debugging the backend
            if "http://localhost:8000" in service_address.url:
                fast_cloud = SocaityUploadAPI(api_key=api_key, upload_endpoint="http://localhost:8000/v0/files")
            else:
                fast_cloud = SocaityUploadAPI(api_key=api_key)
    else:
        st = determine_service_type_from_api_spec(service_address.url)
        ep_req = {
            EndpointSpecification.SOCAITY: RequestHandlerSocaity,
            EndpointSpecification.FASTTASKAPI: RequestHandlerSocaity,
            EndpointSpecification.RUNPOD: RequestHandlerRunpod,
            EndpointSpecification.REPLICATE: RequestHandlerReplicate,
            EndpointSpecification.OTHER: RequestHandler
        }
        if st not in ep_req:
            st = EndpointSpecification.OTHER

        if st == EndpointSpecification.RUNPOD:  # needed in localhost deploy
            service_address = RunpodServiceAddress(service_address.url)

        _rqh = ep_req[st]

    return _rqh(
        service_address=service_address,
        fast_cloud=fast_cloud,
        upload_to_cloud_threshold_mb=upload_to_cloud_threshold_mb,
        api_key=api_key
    )


def determine_service_type_from_api_spec(service_url: str) -> EndpointSpecification:
    """
    Determines the type of service based on the service url.
    :param service_url: The service type is guessed based on the service url
    :param parse_open_api_definition:
        If true and the type can't be determined from the url alone, the openapi.json is parsed to check for fasttaskapi
    """
    # try to get openapi.json to determine the service type
    try:
        parsed = urlparse(service_url)
        openapi_json = httpx.Client().get(f"{parsed.scheme}://{parsed.netloc}/openapi.json").json()
    except Exception as e:
        # must be a normal non-openapi service
        return EndpointSpecification.OTHER
    detail = openapi_json.get('detail', None)
    if detail is not None and 'not found' in detail:
        # Any other non-openapi service
        return EndpointSpecification.OTHER
    info = openapi_json.get("info", "")
    if "fast-task-api" in info and "runpod" in info:
        # socaity service
        return EndpointSpecification.RUNPOD
    # default else
    return EndpointSpecification.FASTTASKAPI
