import functools

from socaity_client.jobs.threaded.internal_job import InternalJob
from socaity_client.utils import get_function_parameters_as_dict
from socaity_client.web.service_client import ServiceClient


class ServiceClientAPI:
    """
    The ServiceClient API uses the service client to perform various tasks.
    1. It uses the service client to make req to the service.
        - It understands the types of the response like socaity job results.
        - In case of a socaity job subsequent req are made to the service until the final server_response is retrieved.
    2. It can batch req.
    3. It makes writing api classes easier.
    """

    def __init__(self, service_client: ServiceClient):
        self.service_client = service_client  # #registry.get_service(service_name_or_service_client)
        self.debug_mode = False  # can be overwritten by using the client_api decorator
        self.start_jobs_immediately = True  # can be overwritten by using the client_api decorator

    def client_api(self):
        """
        The wrapped class gets attributes:
        - start_jobs_immediately: if True, all job will start immediately
        - debug_mode: if True, the job will print debug information
        """
        def decorator(cls):
            cls.start_jobs_immediately = True   # if True, all job will start immediately
            cls.debug_mode = False  # if True, the job will print debug information
            return cls
        return decorator

    def request(self, endpoint_route: str, call_async=True, *args, **kwargs):
        return self.service_client(endpoint_route, call_async, *args, **kwargs)

    def job(self):
        """
        This function will wrap the decorated method with a new "class"
        The new class will have a request method that will be used to call the service.
        The __call__ of that class will be used to create a new internal job and is the same as the decorated method.
        """
        # InternalJob that now is subclass of the class it is decorating
        def decorator(func):
            # remove job_progress from the function signature to display nice for fastapi
            # job_progress_removed = self._job_progress_signature_change(queue_decorated)
            @functools.wraps(func)
            def wrapper(*func_args, **func_kwargs):
                # get the function names of the func and exclude "job" parameters
                params = get_function_parameters_as_dict(
                    func=func,
                    exclude_param_names="job",
                    exclude_param_types=InternalJob,
                    func_args=func_args,
                    func_kwargs=func_kwargs
                )
                # ToDO: if a job func calls another job function, it should not spawn two jobs.
                job = InternalJob(
                    job_function=func,
                    job_params=params,
                    request_function=self.request
                )

                # Set the debug mode and start_jobs_immediately
                debug_mode = self.debug_mode
                start_jobs_immediately = self.start_jobs_immediately
                # check if the first element of func_args is the class instance (self)
                if len(func_args) > 0 and hasattr(func_args[0], "start_jobs_immediately"):
                    debug_mode = func_args[0].debug_mode
                    start_jobs_immediately = func_args[0].start_jobs_immediately

                job.debug_mode = debug_mode
                if start_jobs_immediately:
                    job.run()

                return job
            return wrapper

        return decorator



