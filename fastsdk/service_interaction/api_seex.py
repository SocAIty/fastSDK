from apipod_registry.definitions.service_definitions import (
    EndpointDefinition, ServiceDefinition,
    RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress,
)
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk.service_interaction.response.response_schemas import JOB_RESPONSE_TYPES
from meseex import MrMeseex

import time
from typing import Any, Callable, Optional, Tuple
from datetime import datetime


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
    def response(self):
        """Returns the latest parsed job response from the API, or None."""
        if self.termination_state is not None and isinstance(self.cancel_result, JOB_RESPONSE_TYPES):
            return self.cancel_result

        resp = self.get_task_output("Polling")
        if resp is not None:
            return resp
        return self.get_task_output("Sending request")

    @property
    def runtime_info(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns (delay_seconds, execution_seconds) normalised to seconds."""
        delay_seconds: Optional[float] = None
        execution_seconds: Optional[float] = None

        resp = self.response
        if not resp:
            return None, None

        addr = self.service_def.service_address

        if isinstance(addr, RunpodServiceAddress):
            delay_ms = getattr(resp, "delayTime", None)
            execution_ms = getattr(resp, "executionTime", None)
            if delay_ms is not None:
                delay_seconds = float(delay_ms) / 1000.0
            if execution_ms is not None:
                execution_seconds = float(execution_ms) / 1000.0

        elif isinstance(addr, ReplicateServiceAddress):
            created_str = getattr(resp, "created_at", None)
            started_str = getattr(resp, "started_at", None)
            if created_str and started_str:
                try:
                    t1 = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(str(started_str).replace("Z", "+00:00"))
                    delay_seconds = (t2 - t1).total_seconds()
                except (ValueError, TypeError):
                    pass
            exec_ms = getattr(resp, "execution_time_ms", None)
            if exec_ms is not None:
                execution_seconds = float(exec_ms) / 1000.0

        elif isinstance(addr, SocaityServiceAddress):
            metrics = getattr(resp, "metrics", None)
            if metrics:
                delay_seconds = getattr(metrics, "platform_queue_time_s", None)
                execution_seconds = getattr(metrics, "execution_time_s", None)

        return delay_seconds, execution_seconds

    # ------------------------------------------------------------------
    # Cancellation helpers
    # ------------------------------------------------------------------

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

    def _local_cancel_response(self, message: str) -> dict:
        return {"id": self.meseex_id, "status": "CANCELLED", "error": message}

    def _parse_cancel_response(self, http_response):
        if self._response_parser is None:
            raise RuntimeError("The job is not attached to a response parser")

        error = self._run_async_call(self._response_parser.check_response_status, http_response)
        if error:
            raise ValueError(f"Job cancellation failed: {error}")

        parsed_response = self._run_async_call(self._response_parser.parse_response, http_response, False)
        if isinstance(parsed_response, JOB_RESPONSE_TYPES):
            return parsed_response
        return None

    def _wait_for_remote_cancellation(
        self,
        cancel_response,
        timeout_s: float = 30.0,
        poll_interval_s: float = 0.5,
    ):
        current_response = cancel_response
        deadline = time.monotonic() + timeout_s

        while isinstance(current_response, JOB_RESPONSE_TYPES):
            status = self._api_client.get_status(current_response)

            if status == APIJobStatus.CANCELLED:
                self._meseex_box.cancel_meseex(self, cancel_result=current_response)
                return current_response

            if status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT}:
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
                timeout_s=min(remaining_timeout, 30.0),
            )
            next_response = self._parse_cancel_response(http_response)
            if next_response is None:
                self.set_cancel_result(current_response)
                return current_response

            current_response = next_response

        return current_response

    def cancel(self, wait: bool = False, timeout_s: float = 30.0, poll_interval_s: float = 0.5):
        if self._meseex_box is None or self._api_client is None or self._response_parser is None:
            return super().cancel()

        if self.is_terminal:
            return self.cancel_result or self.response

        current_response = self.response
        has_cancel_url = (
            isinstance(current_response, JOB_RESPONSE_TYPES)
            and self._api_client.get_cancel_url(current_response)
        )

        if not has_cancel_url:
            cancel_response = current_response or self._local_cancel_response("Cancelled before remote job submission")
            self._meseex_box.cancel_meseex(self, cancel_result=cancel_response)
            return cancel_response

        http_response = self._run_async_call(
            self._api_client.cancel_job,
            current_response,
            timeout_s=timeout_s,
        )
        cancel_response = self._parse_cancel_response(http_response)
        if cancel_response is None:
            self.set_cancel_result(current_response)
            return current_response

        status = self._api_client.get_status(cancel_response)

        if status == APIJobStatus.CANCELLED:
            self._meseex_box.cancel_meseex(self, cancel_result=cancel_response)
            return cancel_response

        if status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT}:
            self.set_cancel_result(cancel_response)
            return cancel_response

        self.set_cancel_result(cancel_response)
        if not wait:
            return cancel_response

        return self._wait_for_remote_cancellation(
            cancel_response,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
