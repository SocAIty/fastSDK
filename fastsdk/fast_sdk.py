import functools

from fastCloud import FastCloud
from fastsdk.jobs.threaded.internal_job import InternalJob
from fastsdk.utils import get_function_parameters_as_dict
from fastsdk.web.api_client import APIClient


def fastSDK(
        api_client: APIClient,
        start_jobs_immediately=True
):
    """
    The FastSDK uses the service client to perform various tasks.
    1. It uses the service client to make requests to service endpoints.
        - It understands the types of the response like socaity job results.
        - In case of a socaity job subsequent req are made to the service until the final server_response is retrieved.
    2. It makes writing api classes easier.
    """
    def fastSDK_decorator(cls):
        original_init = cls.__init__

        @functools.wraps(cls)
        def new_init(
                self,
                service: str = None,
                api_key:  str = None,
                fast_cloud: FastCloud = None,
                upload_to_cloud_threshold_mb: float = None,
                max_upload_file_size_mb: float = 1000,
                *args, **kwargs
        ):
            self.api_client = api_client
            self.api_client.add_api_key(service_name=service, key=api_key)

            if service is not None:
                self.api_client._default_service = service
                self.api_client.active_service = service

            if fast_cloud is not None:
                self.api_client.set_fast_cloud(fast_cloud=fast_cloud,
                                                   upload_to_cloud_threshold_mb=upload_to_cloud_threshold_mb,
                                                   max_upload_file_size_mb=max_upload_file_size_mb)
            self.start_jobs_immediately = start_jobs_immediately

            return original_init(self, *args, **kwargs)

        def request(self, endpoint_route: str, call_async=True, *args, **kwargs):
            return self.api_client(endpoint_route, call_async, *args, **kwargs)

        # Add new attributes and methods to the original class
        cls.__init__ = new_init
        cls.request = request

        # Add the docstring to the original class
        # cls.__doc__ =

        return cls

    return fastSDK_decorator


def fastJob(func):
    """
    The wrapped method runs as a threaded internal job.
    A "job" parameter is passed to the function and can be used to send requests with the service client.
    """
    @functools.wraps(func)
    def wrapper(instance, *func_args, **func_kwargs) -> InternalJob:
        # check if the function is called from a fastsdk class:
        if not hasattr(instance, "api_client") or not hasattr(instance, "request"):
            raise RuntimeError("The fastJob decorator can only be used in a class decorated with fastSDK.")

        # get the function names of the func and exclude "job" parameters
        params = get_function_parameters_as_dict(
            func=func,
            exclude_param_names="job",
            exclude_param_types=InternalJob,
            func_args=func_args,
            func_kwargs=func_kwargs
        )
        params["self"] = instance
        # ToDO: if a job func calls another job function, it should not spawn two jobs.
        job = InternalJob(
            job_function=func,
            job_params=params,
            request_function=instance.request
        )
        # Set the debug mode and start_jobs_immediately
        start_jobs_immediately = instance.start_jobs_immediately
        # check if the first element of func_args is the class instance (self)
        if len(func_args) > 0 and hasattr(func_args[0], "start_jobs_immediately"):
            start_jobs_immediately = func_args[0].start_jobs_immediately
        if start_jobs_immediately:
            job.run()
        return job

    # This is a not working approach to provide type hinting in IDEs by just writing one method.
    # get the function names of the func and exclude "job" parameters
    # attach a copy partial func to the class with a signature without the job parameter to be used anywhere else.
    # Create a copy of the original function's signature without the job parameter
    # original_sig = inspect.signature(func)
    # new_params = [
    #     param for name, param in original_sig.parameters.items()
    #     if name != "job" and "InternalJob" not in str(param.annotation)
    # ]
    # # Dynamically create a new signature
    # new_sig = original_sig.replace(parameters=new_params)
    # # Use inspect.Signature to modify the wrapper's signature
    # wrapper.__signature__ = new_sig
    # wrapper.__annotations__ = get_type_hints(func)
    # return wrapper

    return wrapper



