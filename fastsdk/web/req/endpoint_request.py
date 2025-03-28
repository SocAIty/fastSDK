import traceback
from copy import copy
from typing import Union, Any

from httpx import HTTPStatusError

from fastsdk.web.definitions.server_response.base_response import BaseJobResponse, SocaityJobResponse, \
    RunpodJobResponse, JobProgress
from fastsdk.web.definitions.server_response.response_parser import ResponseParser
from fastsdk.web.req.request_handler import RequestHandler
from media_toolkit import MediaFile
from fastsdk.jobs.async_jobs.async_job import AsyncJob
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.server_job_status import ServerJobStatus

import time


class EndPointRequest:
    """
    Some endpoints are async_jobs and return a job id. Others are sync and return the server_response directly.
    Based on the first request response, the class decides with what kind of endpoint it is interacting with.

    In case of a sync job endpoint, the server_response is returned directly.
    In case of an async_jobs job endpoint like the ones that implement the socaity protocol:
        1. The class automatically refreshes the job until it's finished.
        -  The class sends req to the refresh status url until the job is finished.
        -  To do so, it submits more async_jobs req with callbacks with the request handler.
    """
    def __init__(
            self,
            endpoint: EndPoint,
            request_handler: RequestHandler,
            retries_on_error: int = 3
    ):
        self._endpoint = endpoint
        self._request_handler = request_handler

        self._refresh_interval = endpoint.refresh_interval_s
        self._retries_on_error = retries_on_error
        self._current_retry_counter = 0

        # the AsyncJob that is currently executed in the AsyncJobManager as coroutine task
        self._ongoing_async_request = None

        # public attributes to get the server_response
        self.server_response: Union[BaseJobResponse, None] = None
        self.error = None
        self.in_between_server_response = None

        # statistics
        self.first_request_send_at = None
        self.first_response_received_at = None

        # statistic based on server responses (status)
        self.queued_on_server_at = None
        self.processing_on_server_at = None
        self.finished_on_server_at = None

    @property
    def last_refresh_call_at(self):
        if self._ongoing_async_request is None:
            return None
        return self._ongoing_async_request.coroutine_executed_at

    @property
    def last_refresh_call_response_at(self):
        if self._ongoing_async_request is None:
            return None
        return self._ongoing_async_request.future_result_received_at

    @property
    def queue_time_ms(self):
        if self.queued_on_server_at is None:
            return None

        return (self.processing_on_server_at - self.queued_on_server_at).total_seconds() * 1000

    @property
    def processing_time_ms(self):
        if self.processing_on_server_at is None:
            return None
        return (self.finished_on_server_at - self.processing_on_server_at).total_seconds() * 1000

    def request(self, *args, **kwargs):
        """
        Sends a request with the *args, **kwargs to the endpoint with the request handler.
        That submits a coroutine which server_response is retrieved with a callback self._response_callback.
            - In the callback it is checked for errors, response types and if the request is refreshed.
        """
        self._ongoing_async_request = self._request_handler.request_endpoint(
            self._endpoint,
            self._response_callback,
            *args,
            **kwargs
        )
        if self.first_request_send_at is None:
            self.first_request_send_at = self._ongoing_async_request.coroutine_executed_at

    def get_result(self) -> Union[MediaFile, Any, None]:
        """
        Waits until the final server_response is available.
        It only returns the result of the socaity server_response not the meta information.
        If the result is of type FileModel it will be converted into a media-toolkit MediaFile.
        """
        self.wait_until_finished()
        if self.server_response is None:
            return None

        result = self.server_response
        if hasattr(self.server_response, "result"):
            result = self.server_response.result

        if isinstance(result, BaseJobResponse):
            result = result.result

        #if isinstance(result, dict) and "file_name" in result and "content" in result:
        #    try:
        #        return media_from_file_result(result, allow_reads_from_disk=False)
        #    except Exception as e:
        #        print(f"Error in converting the FileModel of server_response: {self.server_response.id} "
        #              f"to MediaFile. Error: {e}")
        #        return result

        return result

    @property
    def progress(self) -> Union[JobProgress, None]:
        """
        Returns the progress of the job along with a message.
        """
        if self.server_response and getattr(self.server_response, "progress", None):
            return self.server_response.progress

        if self.in_between_server_response and getattr(self.in_between_server_response, "progress", None):
            return self.in_between_server_response.progress

        if self.first_request_send_at:
            return JobProgress(progress=0, message="Request sent")
        return JobProgress(progress=0, message="Preparing request")

    def is_finished(self):
        """
        Returns True if the job is finished.
        """
        return self.server_response is not None or self.error is not None

    def wait_until_finished(self):
        """
        This function waits until the job is finished and returns the server_response.
        :return:
        """
        while not self.is_finished():
            time.sleep(0.1)
        return self

    @property
    def job_id(self) -> Union[str, None]:
        """
        Returns: the job id of the server if it is a socaity job, or runpod job id
        Otherwise None.
        """
        if self.server_response is not None and hasattr(self.server_response, "id"):
            return self.server_response.id

        if self.in_between_server_response is not None and hasattr(self.in_between_server_response, "id"):
            return self.in_between_server_response.id

        return None

    def _parse_result_and_refresh_if_necessary(self, async_job_result):
        """
        If job server_response is not of type socaity: it is returned directly.
        If job server_response is of type socaity:
            - It will call the socaity server with the refresh_status function in the return until the job is finished.
            - It checks for socaity request errors.
        """

        if async_job_result is None:
            return self

        # if previously we finished the callback -> it's not the newest server_response
        if self.is_finished():
            return self

        # deal with status errors like Not Found 404 or internal server errors
        rp = ResponseParser()
        request_status_error = rp.check_response_status(async_job_result)
        if request_status_error is not None:
            self.error = request_status_error
            return self

        # Parse the server_response and maybe convert it to BaseJobResponse.
        server_response = rp.parse_response(async_job_result)

        # if not is a socaity job / runpod job, we can return the server_response
        if not isinstance(server_response, BaseJobResponse):
            self.server_response = server_response
            return self

        # check if socaity job / runpod job is finished
        if server_response.status == ServerJobStatus.FINISHED:
            self.in_between_server_response = None
            self.server_response = server_response
            self.finished_on_server_at = copy(self.last_refresh_call_response_at)
            return self
        elif server_response.status == ServerJobStatus.FAILED:
            self.error = server_response.error or "Job failed without error message."
            self.finished_on_server_at = copy(self.last_refresh_call_response_at)
            return self
        elif server_response.status == ServerJobStatus.CANCELLED:
            self.error = "Job was cancelled."
            self.server_response = server_response
            self.finished_on_server_at = copy(self.last_refresh_call_response_at)
            return self

        #### SERVER JOB NOT TERMINED ####
        if server_response.status == ServerJobStatus.QUEUED:
            if self.queued_on_server_at is None:
                self.queued_on_server_at = copy(self.last_refresh_call_response_at)
            else:
                if self.processing_on_server_at is not None:
                    print(f"Job {self.job_id} was added on queue on server, then removed, then readded to server queue")
        elif server_response.status == ServerJobStatus.PROCESSING:
            if self.processing_on_server_at is None:
                self.processing_on_server_at = copy(self.last_refresh_call_response_at)


        # ToDo: Runpod: Deal with unhealthy endpoints.
        # In runpod it might be, that a job starts, then the server crashes and the job goes back into the loop
        # In this case the job is never finished until timout and very likely causes more servers to crash.
        # A solution could be to check if the job changed from queue_to processing and back to queue.
        # Another solution could be to monitor the worker. Check the health of the worker id and if it's unhealthy the job gets cancelled.

        #  REFRESH CALLS -- ASK FOR JOB STATUS AGAIN
        # In this case it was a refresh call
        self.in_between_server_response = server_response

        # if not finished, we need to refresh the job
        # by calling this recursively we can refresh the job until it's finished
        method = 'GET'
        if isinstance(server_response, RunpodJobResponse) or isinstance(server_response, SocaityJobResponse):
            method = 'POST'

        self._ongoing_async_request = self._request_handler.request_url(
            server_response.refresh_job_url,
            method=method,
            callback=self._response_callback,
            delay=self._refresh_interval
        )

    def _deal_with_errors(self, async_job: AsyncJob) -> bool:
        """
        Deals with potential errors. Returns True if the request should be retried.

        """
        # check if the coroutine had an error
        if async_job.error is None:
            return False

        # if there's a HTTPStatusError it means, that the server responded with an error 4.xx or 5.xx
        # in this case we need to decide further.
        if async_job.error is not HTTPStatusError:
            traceback.print_exception(type(async_job.error), async_job.error, async_job.error.__traceback__)
            self.error = async_job.error
            # TODO: check error details and decide if we retry
            return False
        else:  # in case of connection error we try again
            return True

    def _response_callback(self, async_job: AsyncJob):
        """
        This function is called when the first async_jobs job is finished.
        It checks if the server_response is a socaity job server_response and sets the status accordingly.
        :param future: the future object of the async_jobs job
        :return:
        """

        # in this case it was the first request response
        if self.server_response is None and self.in_between_server_response is None:
            self.first_response_received_at = async_job.future_result_received_at
            # If there was an error on the first request stop
            if async_job.error:
                if "Errno 11001" in str(async_job.error):
                    self.error = (f"Error on first request to {self._endpoint.endpoint_route}: "
                                  f"Failed to resolve the server address '{self._request_handler.service_address.url}'."
                                  f" Host not resolvable. Check internet connection and service url. "
                                  f"Details: {async_job.error}")
                else:
                    error_msg = f"Error on first request to {self._endpoint.endpoint_route}: {async_job.error}"
                    tb = traceback.TracebackException.from_exception(async_job.error)
                    error_msg += "\n" + ''.join(tb.format())
                    self.error = error_msg
                return self

        # normal refresh
        if async_job.error is None:
            return self._parse_result_and_refresh_if_necessary(async_job.result)

        # decide if and retry the request.
        retry = self._deal_with_errors(async_job)
        if retry:
            # TODO: implement retry logic for other endpoint types than socaity
            # for socaity
            if (self.in_between_server_response is not None
                    and isinstance(self.in_between_server_response, BaseJobResponse)):
                self._current_retry_counter += 1
                if self._current_retry_counter < self._retries_on_error:
                    # use previous job server_response to retry
                    return self._parse_result_and_refresh_if_necessary(self.in_between_server_response)
                else:
                    self.error = async_job.error
                    return self
