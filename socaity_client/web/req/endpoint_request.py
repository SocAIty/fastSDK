from httpx import HTTPStatusError

from socaity_client.jobs.async_jobs.async_job import AsyncJob
from socaity_client.web.definitions.endpoint import EndPoint
from socaity_client.web.definitions.socaity_server_response import SocaityServerResponse, SocaityServerJobStatus
from socaity_client.web.req.request_handler import RequestHandler
from socaity_client.web.req.server_response_parser import parse_response, has_request_status_code_error
import time

class EndPointRequest:
    """
    Some endpoints are async_jobs and return a job id. Others are sync and return the result directly.
    Based on the first request response, the class decides with what kind of endpoint it is interacting with.

    In case of a sync job endpoint, the result is returned directly.
    In case of an async_jobs job endpoint like the ones that implement the socaity protocol:
        1. The class automatically refreshes the job until it's finished.
        -  The class sends req to the refresh status url until the job is finished.
        -  To do so, it submits more async_jobs req with callbacks with the request handler.
    """
    def __init__(
            self,
            endpoint: EndPoint,
            request_handler: RequestHandler,
            refresh_interval: float = 0.5,
            retries_on_error: int = 3
    ):
        self._endpoint = endpoint
        self._request_handler = request_handler

        self._refresh_interval = refresh_interval
        self._retries_on_error = retries_on_error
        self._current_retry_counter = 0

        # the AsyncJob that is currently executed in the AsyncJobManager as coroutine task
        self._ongoing_async_request = None

        # public attributes to get the result
        self.result = None
        self.error = None
        self.in_between_result = None

        # statistics
        self.first_request_send_at = None
        self.first_response_received_at = None

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

    def request(self, *args, **kwargs):
        """
        Sends a request with the *args, **kwargs to the endpoint with the request handler.
        That submits a coroutine which result is retrieved with a callback self._response_callback.
            - In the callback it is checked for errors, response types and if the request is refreshed.
        """
        self._ongoing_async_request = self._request_handler.request_endpoint_async(
            self._endpoint,
            callback=self._response_callback,
            *args,
            **kwargs
        )
        self.first_request_send_at = self._ongoing_async_request.coroutine_executed_at

    def is_finished(self):
        """
        Returns True if the job is finished.
        """
        return self.result is not None or self.error is not None

    def wait_until_finished(self):
        """
        This function waits until the job is finished and returns the result.
        :return:
        """
        while not self.is_finished():
            time.sleep(0.1)
        return self

    def _parse_result_and_refresh_if_necessary(self, async_job_result):
        """
        If job result is not of type socaity: it is returned directly.
        If job result is of type socaity:
            - It will call the socaity server with the refresh_status function in the return until the job is finished.
            - It checks for socaity request errors.

        If the request was successfull it re
        """

        if async_job_result is None:
            return self

        # if previously we finished the callback -> it's not the newest result
        if self.is_finished():
            return self

        # deal with status errors like Not Found 404 or internal server errors
        request_status_error = has_request_status_code_error(async_job_result)
        if request_status_error is not False:
            self.error = request_status_error
            return self

        # Parse the result and convert it to SocaityServerResponse if is that response type.
        job_result = parse_response(async_job_result)
        # if not is a socaity job, we can return the result
        if not isinstance(job_result, SocaityServerResponse):
            self.result = job_result
            return self
        # check if socaity job is finished
        if job_result.status == SocaityServerJobStatus.FINISHED:
            self.in_between_result = None
            self.result = job_result
            return self
        elif job_result.status == SocaityServerJobStatus.FAILED:
            self.error = job_result.message
            if job_result.message is None:
                self.error = "Job failed without error message."

            return self

        # In this case it was a refresh call
        self.in_between_result = job_result
        # if not finished, we need to refresh the job
        # by calling this recursively we can refresh the job until it's finished
        refresh_url = self._request_handler.service_url + job_result.refresh_job_url
        self._ongoing_async_request = self._request_handler.request_url_async(
            refresh_url,
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
            self.error = async_job.error
            # TODO: check error details and decide if we retry
            return False
        else:  # in case of connection error we try again
            return True

    def _response_callback(self, async_job: AsyncJob):
        """
        This function is called when the first async_jobs job is finished.
        It checks if the result is a socaity job result and sets the status accordingly.
        :param future: the future object of the async_jobs job
        :return:
        """

        # in this case it was the first request response
        if self.result is None and self.in_between_result is None:
            self.first_response_received_at = async_job.future_result_received_at
            # If there was an error on the first request stop
            if async_job.error:
                self.error = f"Error on first request to {self._endpoint.endpoint_route}: {async_job.error}"
                return self

        # normal refresh
        if async_job.error is None:
            return self._parse_result_and_refresh_if_necessary(async_job.result)

        # decide if and retry the request.
        retry = self._deal_with_errors(async_job)
        if retry:
            # TODO: implement retry logic for other endpoint types than socaity
            # for socaity
            if self.in_between_result is not None and isinstance(self.in_between_result, SocaityServerResponse):
                self._current_retry_counter += 1
                if self._current_retry_counter < self._retries_on_error:
                    # use previous job result to retry
                    return self._parse_result_and_refresh_if_necessary(self.in_between_result)
                else:
                    self.error = async_job.error
                    return self
