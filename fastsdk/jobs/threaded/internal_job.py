import inspect
import itertools
import time
import traceback
from datetime import datetime
from typing import Union
from uuid import uuid4
from tqdm import tqdm

from fastsdk.jobs.threaded.internal_job_manager import InternalJobManager
from fastsdk.jobs.threaded.job_status import JOB_STATUS
from fastsdk.jobs.threaded.job_progress import JobProgress
from fastsdk.web.req.endpoint_request import EndPointRequest


class InternalJob:
    def __init__(
            self,
            job_function: callable,
            job_params: Union[dict, None],
            request_function: callable = None
    ):
        """
        Functionality threaded job_function with status tracking.
        An internal job stores a reference to a job_function and its parameters.
        With run() the job_function is threaded. The internal job keeps track of its status, progress and server_response.

        Functionality to send requests:
        The job can be used to send requests. The job is passed to a wrapped function that uses job as parameter
            If the job_function uses the internal job to send requests, the job also keeps track of these requests.

        :_job_function (callable): The function to be called threaded
        :_job_params (dict): Parameters for the function call
        :request_function (callable): Function to send requests.
        """
        self.id = str(uuid4())
        self._job_function = job_function
        self._job_params = job_params
        self.status: JOB_STATUS = JOB_STATUS.CREATED
        self.job_progress = JobProgress()

        # overwrite request function
        self._request_function = request_function
        self._ongoing_async_request: Union[EndPointRequest, None] = None

        self.result = None
        self.error = None

        # statistics
        self.created_at = datetime.utcnow()
        self.queued_at = None
        self.started_at = None
        self.finished_at = None

    def request(self, endpoint_route: str, *args, **kwargs) -> EndPointRequest:
        self._ongoing_async_request = self._request_function(endpoint_route, True, *args, **kwargs)
        return self._ongoing_async_request

    def request_sync(self, endpoint_route: str, *args, **kwargs) -> EndPointRequest:
        endpoint_request = self.request(endpoint_route, *args, **kwargs)
        endpoint_request.wait_until_finished()
        return endpoint_request

    def get_result(self, print_progress: bool = True, throw_error: bool = True):
        """
        Waits until the job is finished and returns the result of the underlying threaded function.
        :param print_progress: If true, the progress is printed.
        :param throw_error: If true, the error is raised if the job failed.
        """

        spinning_wheel = itertools.cycle(['◐', '◐', '◓', '◓', '◑', '◑', '◒', '◒'])
        if print_progress:
            pbar = tqdm(total=100, bar_format="{desc}")
            desc = f"{self._job_function.__name__}, status: initializing, {next(spinning_wheel)}"
            pbar.set_description(desc)

        job_id = None
        while not self.finished():
            job_id = (
                self._ongoing_async_request.job_id
                if self._ongoing_async_request and self._ongoing_async_request.job_id
                else None
            )
            if print_progress:
                if job_id is None:
                    desc = f"{self._job_function.__name__}, status: preparing request, {next(spinning_wheel)}"
                else:
                    progress, message = self.progress
                    if progress > 0:
                        desc = (
                            f"{self._job_function.__name__}, job_id: {job_id}, "
                            f"status []: {self.status.name}, progress: {progress:.0%},  {next(spinning_wheel)}"
                        )
                    else:
                        desc = (
                            f"{self._job_function.__name__}, job_id: {job_id}, "
                            f"status: {self.status.name}, {next(spinning_wheel)}"
                        )
                pbar.set_description(desc)
                time.sleep(0.1)

        if print_progress:
            progress, message = self.progress
            if self.status is JOB_STATUS.FINISHED and job_id:
                final_desc = (
                    f"{self._job_function.__name__}, job_id: {job_id}, "
                    f"status: {self.status.name}, progress: {progress:.0%}"
                )
            else:
                final_desc = f"{self._job_function.__name__}, status: {self.status.name}"

            pbar.set_description(final_desc)
            pbar.close()

        if self.status == JOB_STATUS.FAILED and throw_error:
            raise self.error

        return self.result

    def finished(self):
        """
        Returns true if job has ended. Either completed or by error.
        """
        return self.status in [JOB_STATUS.FINISHED, JOB_STATUS.FAILED]

    def has_started(self):
        return self.status in [JOB_STATUS.QUEUED, JOB_STATUS.PROCESSING]

    def wait_for_finished(
            self,
            wait_for_request_result: bool = False
    ):
        """
        This waits until the underlying _job function returns a server_response.
        :param wait_for_request_result: If there was a request send with the request function, this waits also until the server_response is finished.
        """
        if not self.has_started() and not self.finished():
            self.run()

        if wait_for_request_result:
            self.wait_for_request_result()

        while not self.finished():
            time.sleep(0.1)
        return self

    def wait_for_request_result(self):
        """
        Waits until the request send with the job argument is finished.
        """
        if self._ongoing_async_request is None:
            return None

        return self._ongoing_async_request.wait_until_finished()

    @property
    def progress(self) -> tuple[float, str]:
        """
        Returns the job's progress and status message.
        """
        if self._ongoing_async_request:
            return self._ongoing_async_request.progress
        return self.job_progress.get_progress()

    def set_progress(self, progress: float, message: str = None):
        self.job_progress.set_progress(progress, message)

    def _add_job_progress_to_kwargs(self):
        for param in inspect.signature(self._job_function).parameters.values():
            if param.annotation == InternalJob or param.name == "job":
                self._job_params[param.name] = self

        return self._job_params

    def _run(self):
        """
        function is called by internal job manager when job is executed
        """
        # run job
        self.started_at = datetime.utcnow()
        self.status = JOB_STATUS.PROCESSING

        try:
            self._add_job_progress_to_kwargs()  # add to job to jub_function if is in signature
            self.result = self._job_function(**self._job_params)
            self.set_progress(1.0, None)
            self.status = JOB_STATUS.FINISHED
        except Exception as e:
            self.status = JOB_STATUS.FAILED
            self.error = e
            self.finished_at = datetime.utcnow()
            print(traceback.format_exc())

    def run_sync(self):
        return self.run(run_async=False)

    def run(self, run_async: bool = True):
        InternalJobManager.submit(self)
        if not run_async:
            self.wait_for_finished()
        return self


