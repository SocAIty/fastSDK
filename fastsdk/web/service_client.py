import inspect
from typing import Union, Tuple
from urllib.parse import urlparse
import httpx

from fastCloud import CloudStorage
from fastsdk.definitions.enums import EndpointSpecification
from fastsdk.settings import API_KEYS
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.definitions.ai_model import AIModelDescription
from fastsdk.web.req.endpoint_request import EndPointRequest

from fastsdk.registry import Registry
from fastsdk.web.req.request_handler import RequestHandler
from fastsdk.web.req.request_handler_runpod import RequestHandlerRunpod


class ServiceClient:
    """
    The ServiceClient is used to interact with a service and its endpoints.
    A service usually has multiple endpoints with different routes.
    The ServiceClient makes it easy to add and call these endpoints.
    """
    def __init__(
            self,
            # required information for execution
            service_urls: Union[dict, str, list],
            default_service: str = "localhost",
            # optional information for documentation and services
            service_name: str = None,
            service_description: str = None,
            model_description: AIModelDescription = None,
            # optional args for s3 upload and co.
            cloud_storage: CloudStorage = None,
            upload_to_cloud_storage_threshold_mb: int = 10,
            api_keys: dict = None,
            *args,
            **kwargs
    ):
        """
        Initialize the ServiceClient with the required information.
        :param service_urls: urls to possible hosts of the service api. Structured as { service_url_nickname: url }
        :param default_service: which of the services to use
        :param service_name: the name of the service. Used to find the service in the registry.
        :param service_description: a description of the service.
        :param model_description: a description of the model used in the service. Used for documentation.
        :param cloud_storage: if specified, files will be uploaded to azure / s3 for file transfer instead of sending them as bytes directly.
             Then a file_url is sent to the endpoint instead of the file as bytes.
             Property can be overwritten with the fast_sdk init of the service.
        :param upload_to_cloud_storage_threshold_mb:  if the combined file size is greater than this limit, the file is uploaded to the cloud handler.
        :param api_keys: dictionary structured as {service_url_nickname: api_key} to add api keys to the service.
        """
        # definitions and registry
        self.service_description = service_description
        self.model = model_description
        # create the service urls
        self.service_urls = self._create_service_urls(service_urls)
        self._default_service = default_service

        # add api keys for authorization
        # If nothing is specified we use the default api keys defined by environment variables
        if api_keys is None:
            api_keys = { name: val for name, val in API_KEYS.items() if val is not None }
        self.api_keys = api_keys

        # init request handler
        self._request_handler = None
        self.service_url = None
        self._cloud_handler = cloud_storage
        self._upload_to_cloud_handler_limit_mb = upload_to_cloud_storage_threshold_mb
        self.set_service(default_service)

        # add the service client to the registry. This makes it easier to find them later on.
        self.service_name = service_name if service_name is not None else self.service_url
        Registry().add_service(service_name, self)

        self.endpoint_request_funcs = {}  # { endpoint_name: function, endpoint_name_async: function }
        self.endpoints = {}  # { endpoint_name: endpoint }

    def set_service(self, service_name: str = None):
        """
        Set the service to send requests to. Instantiates the request handler.
        Caution: changing service while requests are ongoing might result in unexpected behaviour.
        :param service_name: the url of the service
        """
        if service_name is None and self._default_service in self.service_urls:
            service_name = self._default_service

        if service_name not in self.service_urls:
            print(f"Service {service_name} not found in the service urls {self.service_urls}."
                  f"Using {list(self.service_urls.keys())[0]} instead.")
            service_name = list(self.service_urls.keys())[0]

        self.service_url = self.service_urls[service_name]

        # create new request handler if necessary; or use the existing one
        if self._request_handler is None or self._request_handler.service_url != self.service_url:
            # first check if api key is in our list of global api keys settings.API_KEYS
            api_key = self.api_keys.get(service_name, None) if self.api_keys is not None else None

            self._request_handler = create_request_handler(
                service_url=self.service_url,
                cloud_storage=self._cloud_handler,
                upload_to_cloud_storage_threshold_mb=10,
                api_key=api_key
            )

        return self

    def add_api_key(self, name: str, key: str):
        if key is None or name is None or len(key) == 0:
            return self.api_keys

        if self.api_keys is None:
            self.api_keys = {name: key}
        else:
            self.api_keys[name] = key
        return self.api_keys

    def set_cloud_storage(self, cloud_storage: CloudStorage, upload_to_cloud_threshold: int = 10):
        """
        Set the cloud handler for the service. Used to upload / download files to the cloud handler.
        :param cloud_storage: the cloud storage to use.
        """
        self._cloud_handler = cloud_storage
        self._upload_to_cloud_handler_limit_mb = upload_to_cloud_threshold
        # update the request handler
        self._request_handler.set_cloud_storage(cloud_storage, upload_to_cloud_threshold)

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
            endpoint_request = EndPointRequest(
                endpoint=endpoint,
                request_handler=self._request_handler,
                retries_on_error=retries_on_error
            )
            endpoint_request.request(*args, **kwargs)
            if not is_async:
                endpoint_request.wait_until_finished()

            return endpoint_request

        # create method parameters
        ep_args = endpoint.params()
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
        # Create a partial function with default values as None
        #func_name = f"{endpoint.endpoint_route}" if not is_async else f"{endpoint.endpoint_route}_async"
        #partial_func = functools.partial(endpoint_job_wrapper, **{name: t for name, t in ep_args.items()})
        ## Set the function name
        #partial_func.__name__ = func_name
        #sig_params = [inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ptype) for name, ptype
        #              in ep_args.items()]
        #partial_func.__signature__ = inspect.Signature(parameters=sig_params)
#
        ## add method to class
        #bound_method = types.MethodType(partial_func, self)
        #self.__setattr__(partial_func.__name__, bound_method)
        #self.endpoint_request_funcs[partial_func.__name__] = partial_func

        #return partial_func

    def _add_endpoint(self, endpoint: EndPoint) -> Tuple[callable, callable]:
        """
        Adds and endpoint and convenience functions to an service
        You can call the ServiceClient.endpoint_function_name to send a request to the endpoint and wait for the server_response.
        Use the ServiceClient.endpoint_function_name_async to send a request and get an asyncio_task object.
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
            get_params: dict = None,
            post_params: dict = None,
            file_params: dict = None,
            timeout: int = 3600,
            refresh_interval: float = 0.5
    ):
        ep = EndPoint(
            endpoint_route=endpoint_route,
            get_params=get_params,
            post_params=post_params,
            file_params=file_params,
            timeout=timeout,
            refresh_interval=refresh_interval
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
    def _create_service_urls(service_urls: Union[dict, str, list]):
        # set service urls and fix them if necessary
        if isinstance(service_urls, str):
            service_urls = {"0": service_urls}
        elif isinstance(service_urls, list):
            service_urls = {str(i): url for i, url in enumerate(service_urls)}

        # fix problems with "handwritten" urls
        service_urls = {k: ServiceClient._url_sanitize(url) for k, url in service_urls.items()}
        return service_urls

    @staticmethod
    def _url_sanitize(url: str):
        """
        Add http: // if not present and remove trailing slash
        """
        url = url if url[-1] != "/" else url[:-1]
        if not url.startswith("http") and not url.startswith("https"):
            url = f"http://{url}"
        return url

    def __call__(self, endpoint_route: str, call_async: bool = False, *args, **kwargs) -> EndPointRequest:
        """
        Call a function synchronously by name.
        :param endpoint_route: the name of the function
        :param args: the arguments to pass to the function
        :param kwargs: the keyword arguments to pass to the function
        :return: the server_response of the function
        """
        if call_async:
            endpoint_route = f"{endpoint_route}_async" if not endpoint_route.endswith("_async") else endpoint_route

        if endpoint_route not in self.endpoint_request_funcs:
            raise ValueError(f"Function {endpoint_route} not found in the service.")

        return self.endpoint_request_funcs[endpoint_route](*args, **kwargs)

    def __del__(self):
        """
        Remove the service from the registry when the object is deleted.
        """
        Registry().remove_service(self.service_name)


def create_request_handler(
        service_url: str,
        api_key: dict = None,
        cloud_storage: CloudStorage = None,
        upload_to_cloud_storage_threshold_mb: int = 10
) -> RequestHandler:
    st = determine_service_type(service_url)
    ep_req = {
        EndpointSpecification.FASTTASKAPI: RequestHandler,
        EndpointSpecification.RUNPOD: RequestHandlerRunpod,
        EndpointSpecification.OTHER: RequestHandler
    }
    if st not in ep_req:
        st = EndpointSpecification.OTHER

    return ep_req[st](
        service_url=service_url,
        cloud_handler=cloud_storage,
        upload_to_cloud_storage_threshold_mb=upload_to_cloud_storage_threshold_mb,
        api_key=api_key
    )


def determine_service_type(service_url: str, parse_open_api_definition: bool = True) -> EndpointSpecification:
    """
    Determines the type of service based on the service url.
    :param service_url: The service type is guessed based on the service url
    :param parse_open_api_definition:
        If true and the type can't be determined from the url alone, the openapi.json is parsed to check for fasttaskapi
    """
    # case hosted on runpod
    if "api.runpod.ai" in service_url:
        return EndpointSpecification.RUNPOD

    if "api.replicate.com" in service_url:
        return EndpointSpecification.REPLICATE

    if not parse_open_api_definition:
        return EndpointSpecification.OTHER

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
