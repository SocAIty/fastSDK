from typing import Union, Any

from httpx import HTTPStatusError

from multimodal_files import MultiModalFile
from multimodal_files.file_conversion import from_file_result
from socaity_client.jobs.async_jobs.async_job import AsyncJob
from socaity_client.web.definitions.endpoint import EndPoint
from socaity_client.web.definitions.socaity_server_response import SocaityServerResponse, SocaityServerJobStatus
from socaity_client.web.req.request_handler import RequestHandler
from socaity_client.web.req.server_response_parser import parse_response, has_request_status_code_error
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

        # public attributes to get the server_response
        self.server_response = None
        self.error = None
        self.in_between_server_response = None

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
        That submits a coroutine which server_response is retrieved with a callback self._response_callback.
            - In the callback it is checked for errors, response types and if the request is refreshed.
        """
        self._ongoing_async_request = self._request_handler.request_endpoint_async(
            self._endpoint,
            callback=self._response_callback,
            *args,
            **kwargs
        )
        self.first_request_send_at = self._ongoing_async_request.coroutine_executed_at

    def get_result(self) -> Union[MultiModalFile, Any, None]:
        """
        Waits until the final server_response is available.
        It only returns the result of the socaity server_response not the meta information.
        If the result is of type FileResult it will be converted into a multimodal file.
        """
        self.wait_until_finished()
        if self.server_response is None:
            return None

        result = self.server_response.result
        if isinstance(result, SocaityServerResponse):
            result = result.result

        if isinstance(result, dict) and "file_name" in result and "content" in result:
            return from_file_result(result)

        return result


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

    def _parse_result_and_refresh_if_necessary(self, async_job_result):
        """
        If job server_response is not of type socaity: it is returned directly.
        If job server_response is of type socaity:
            - It will call the socaity server with the refresh_status function in the return until the job is finished.
            - It checks for socaity request errors.

        If the request was successfull it re
        """

        if async_job_result is None:
            return self

        # if previously we finished the callback -> it's not the newest server_response
        if self.is_finished():
            return self

        # deal with status errors like Not Found 404 or internal server errors
        request_status_error = has_request_status_code_error(async_job_result)
        if request_status_error is not False:
            self.error = request_status_error
            return self

        # Parse the server_response and convert it to SocaityServerResponse if is that response type.
        server_response = parse_response(async_job_result)
        # if not is a socaity job, we can return the server_response
        if not isinstance(server_response, SocaityServerResponse):
            self.server_response = server_response
            return self

        # check if socaity job is finished
        if server_response.status == SocaityServerJobStatus.FINISHED:
            self.in_between_server_response = None
            self.server_response = server_response
            return self
        elif server_response.status == SocaityServerJobStatus.FAILED:
            self.error = server_response.message
            if server_response.message is None:
                self.error = "Job failed without error message."

            return self

        # In this case it was a refresh call
        self.in_between_server_response = server_response
        # if not finished, we need to refresh the job
        # by calling this recursively we can refresh the job until it's finished
        refresh_url = self._request_handler.service_url + server_response.refresh_job_url
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
        It checks if the server_response is a socaity job server_response and sets the status accordingly.
        :param future: the future object of the async_jobs job
        :return:
        """

        # in this case it was the first request response
        if self.server_response is None and self.in_between_server_response is None:
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
            if self.in_between_server_response is not None and isinstance(self.in_between_server_response, SocaityServerResponse):
                self._current_retry_counter += 1
                if self._current_retry_counter < self._retries_on_error:
                    # use previous job server_response to retry
                    return self._parse_result_and_refresh_if_necessary(self.in_between_server_response)
                else:
                    self.error = async_job.error
                    return self
