import functools

from fastCloud import CloudStorage
from fastsdk.jobs.threaded.internal_job import InternalJob
from fastsdk.utils import get_function_parameters_as_dict
from fastsdk.web.service_client import ServiceClient


def fastSDK(
        service_client: ServiceClient,
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
                service: str = "localhost",
                cloud_storage: CloudStorage = None,
                upload_to_cloud_threshold: int = 10,
                api_key:  str = None,
                *args, **kwargs
        ):
            self.service_client = service_client
            self.service_client.add_api_key(name=service, key=api_key)
            self.service_client.set_service(service)
            self.service_client.set_cloud_storage(cloud_storage, upload_to_cloud_threshold=upload_to_cloud_threshold)
            self.start_jobs_immediately = start_jobs_immediately
            return original_init(self, *args, **kwargs)

        def request(self, endpoint_route: str, call_async=True, *args, **kwargs):
            return self.service_client(endpoint_route, call_async, *args, **kwargs)

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
        if not hasattr(instance, "service_client") or not hasattr(instance, "request"):
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
    return wrapper


