from apipod_registry.definitions.service_definitions import EndpointDefinition, ServiceDefinition
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk.service_interaction.response.base_response import BaseJobResponse
from meseex import MrMeseex

import time
from typing import Any, Callable, Optional


class APISeex(MrMeseex):
    """Meseex extension specifically for API job handling."""
    def __init__(
        self,
        service_def: ServiceDefinition,
        endpoint_def: EndpointDefinition,
        data: Any = None,
        name: str = None,
        tasks: list = None,
        cancel_handler: Callable[..., Any] = None,
    ):
        super().__init__(tasks, data, name, cancel_handler)
        self.service_def = service_def
        self.endpoint_def = endpoint_def

    @property
    def response(self) -> Optional[BaseJobResponse]:
        """Returns the latest parsed response from the API."""
        if self.termination_state is not None and isinstance(self.cancel_result, BaseJobResponse):
            return self.cancel_result

        resp = self.get_task_output("Polling")
        if resp is not None:
            return resp
        return self.get_task_output("Sending request")

    def _run_async_call(self, method, *args, timeout_s: float = 30.0):
        if self._meseex_box is None:
            raise RuntimeError("The job is not attached to a MeseexBox runtime")

        task = self._meseex_box.task_executor.submit(method, *args)
        started_at = time.monotonic()

        while not task.is_completed:
            if timeout_s is not None and (time.monotonic() - started_at) > timeout_s:
                task.cancel()
                raise TimeoutError("Timed out while waiting for cancellation request")
            time.sleep(0.01)

        if task.error is not None:
            raise task.error

        return task.result

    def _local_cancel_response(self, message: str) -> BaseJobResponse:
        return BaseJobResponse(
            id=self.meseex_id,
            status=APIJobStatus.CANCELLED,
            error=message,
            service_specification=self.service_def.specification
        )

    def _parse_cancel_response(self, http_response) -> Optional[BaseJobResponse]:
        if self._response_parser is None:
            raise RuntimeError("The job is not attached to a response parser")

        error = self._response_parser.check_response_status(http_response)
        if error:
            raise ValueError(f"Job cancellation failed: {error}")

        parsed_response = self._response_parser.parse_response(http_response, parse_media=False)
        if isinstance(parsed_response, BaseJobResponse):
            return parsed_response
        return None

    def _wait_for_remote_cancellation(
        self,
        cancel_response: BaseJobResponse,
        timeout_s: float = 30.0,
        poll_interval_s: float = 0.5
    ):
        current_response = cancel_response
        deadline = time.monotonic() + timeout_s

        while isinstance(current_response, BaseJobResponse):
            if current_response.status == APIJobStatus.CANCELLED:
                self._meseex_box.cancel_meseex(self, cancel_result=current_response)
                return current_response

            if current_response.status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT}:
                self.set_cancel_result(current_response)
                return current_response

            remaining_timeout = deadline - time.monotonic()
            if remaining_timeout <= 0:
                self.set_cancel_result(current_response)
                return current_response

            time.sleep(min(poll_interval_s, remaining_timeout))
            http_response = self._run_async_call(
                self._api_client.poll_status,
                current_response,
                timeout_s=min(remaining_timeout, 30.0)
            )
            next_response = self._parse_cancel_response(http_response)
            if next_response is None:
                self.set_cancel_result(current_response)
                return current_response

            current_response = next_response

        return current_response

    def cancel(self, wait: bool = False, timeout_s: float = 30.0, poll_interval_s: float = 0.5):
        print(f"DEBUG: ApiJobManager.cancel called with wait={wait}")
        if self._meseex_box is None or self._api_client is None or self._response_parser is None:
            return super().cancel()

        if self.is_terminal:
            return self.cancel_result or self.response

        current_response = self.response
        if not isinstance(current_response, BaseJobResponse) or not current_response.cancel_job_url:
            cancel_response = current_response or self._local_cancel_response("Cancelled before remote job submission")
            self._meseex_box.cancel_meseex(self, cancel_result=cancel_response)
            return cancel_response

        http_response = self._run_async_call(
            self._api_client.cancel_job,
            current_response,
            timeout_s=timeout_s
        )
        cancel_response = self._parse_cancel_response(http_response)
        if cancel_response is None:
            self.set_cancel_result(current_response)
            return current_response

        if cancel_response.status == APIJobStatus.CANCELLED:
            self._meseex_box.cancel_meseex(self, cancel_result=cancel_response)
            return cancel_response

        if cancel_response.status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT}:
            self.set_cancel_result(cancel_response)
            return cancel_response

        self.set_cancel_result(cancel_response)
        if not wait:
            return cancel_response

        return self._wait_for_remote_cancellation(
            cancel_response,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s
        )