import functools
import inspect
import types
from typing import Union, Tuple

from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.definitions.enums import EndpointSpecification
from fastsdk.definitions.ai_model import AIModelDescription
from fastsdk.web.req.endpoint_request import EndPointRequest

from fastsdk.web.req.request_handler import RequestHandler


class ServiceClient:
    """
    The ServiceClient is used to interact with a service and its endpoints.
    A service usually has multiple endpoints with different routes.
    The ServiceClient makes it easy to add and call these endpoints.
    """

    def __init__(
            self,
            # required information for execution
            service_url: str = None,
            service_specification: Union[EndpointSpecification, str] = EndpointSpecification.SOCAITY,
            # optional information for documentation and services
            model_description: AIModelDescription = None,
            *args,
            **kwargs
    ):
        """
        Initialize the ServiceClient with the required information.
        :param service_url: the url of the service api
        :param service_specification: based on the service specs, the ServiceClient behaves differently.
            In case of socaity it will for example add the status endpoint. This one can be used to check server health.
        :param model_name: used for documentation
        :param model_domain_tags: find the model easier in the registry
        :param model_tags: find the model easier in the registry
        """
        # definitions and registry
        self.model = model_description
        self.endpoint_specification = service_specification  # the default value - used in the endpoint_decorator

        # service_url add http:// if not present and remove trailing slash
        service_url = service_url if service_url[-1] != "/" else service_url[:-1]
        if not service_url.startswith("http") or not service_url.startswith("https"):
            service_url = f"http://{service_url}"

        self._request_handler = RequestHandler(service_url=service_url)

        self.endpoint_request_funcs = {}  # { endpoint_name: function, endpoint_name_async: function }
        self.endpoints = {}  # { endpoint_name: endpoint }

    def _create_endpoint_func(
            self,
            endpoint: EndPoint,
            is_async: bool = False,
            refresh_interval: float = 1.0,
            retries_on_error: int = 3
    ):
        """
        Creates a new function to call an endpoint and adds it to the class.
        :param endpoint: the definition of the endpoint
        :param is_async: if the endpoint is called async_jobs or sync
        :param refresh_interval: if the service returns an async_jobs job (with job_id),
                the refresh interval is used to check for updates
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
                refresh_interval=refresh_interval,
                retries_on_error=retries_on_error
            )
            endpoint_request.request(*args, **kwargs)
            if not is_async:
                endpoint_request.wait_until_finished()

            return endpoint_request

        # create method parameters
        ep_args = endpoint.params()
        ep_args.update(endpoint.post_params)
        ep_args.update(endpoint.file_params)

        # Create a partial function with default values as None
        func_name = f"{endpoint.endpoint_route}" if not is_async else f"{endpoint.endpoint_route}_async"
        partial_func = functools.partial(endpoint_job_wrapper, **{name: None for name in ep_args.keys()})
        # Set the function name
        partial_func.__name__ = func_name
        sig_params = [inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ptype) for name, ptype
                      in ep_args.items()]
        partial_func.__signature__ = inspect.Signature(parameters=sig_params)

        # add method to class
        bound_method = types.MethodType(partial_func, self)
        self.__setattr__(partial_func.__name__, bound_method)
        self.endpoint_request_funcs[partial_func.__name__] = partial_func

        return partial_func

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
            timeout: int = 3600):
        ep = EndPoint(
            endpoint_route=endpoint_route,
            get_params=get_params,
            post_params=post_params,
            file_params=file_params,
            timeout=timeout)
        self._add_endpoint(ep)

    def list_endpoints(self) -> dict:
        """
        List all available endpoints of the service with their parameters.
        :return: a list of endpoint names
        """
        for name, func in self.endpoint_request_funcs.items():
            print(f"{name}: {func.__signature__}")
        return self.endpoint_request_funcs

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



