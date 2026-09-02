"""Meseex task implementations for the API job pipeline."""

import logging
from typing import Any, Dict

from meseex.control_flow import polling_task, PollAgain
from socaity_schemas import JOB_RESPONSE_TYPES, StreamingResponse
from media_toolkit import MediaDict

from fastsdk.profiling import event as profile_event, start as profile_start
from fastsdk.service_interaction.api_seex import APISeex
from fastsdk.service_interaction.request import RequestData
from fastsdk.service_interaction.response.api_job_status import APIJobStatus


logger = logging.getLogger(__name__)

# Provider status GETs (Replicate in particular) return 503/429 while the
# prediction already exists. Treat those like transport errors: PollAgain,
# not a failed Socaity job.
TRANSIENT_POLL_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def retry_poll_or_raise(job: APISeex, error: BaseException) -> PollAgain:
    data = job.get_task_data() or {}
    n_polling_errors = data.get("number_of_polling_errors", 0) if isinstance(data, dict) else 0
    if n_polling_errors > 3:
        raise error
    job.set_task_data({"number_of_polling_errors": n_polling_errors + 1})
    return PollAgain(f"Job status polling failed: {error}")


class JobTasks:
    """Async task handlers wired into ``MeseexBox`` for API jobs.

    Meseex always passes the job ticket as the handler's first argument after
    ``self``. Runtime type is ``APISeex``; the annotation must stay a concrete
    ``MrMeseex`` subclass (not a string forward ref) so meseex detects it.
    ``@polling_task`` stays on instance methods because the decorator only
    supports ``(job)`` or ``(self, job)`` call shapes.

    Handlers read the provider stack from the job, which binds it at submit
    time. Re-resolving per task could hand a job another tenant's credential.
    """

    def as_task_map(self) -> Dict[str, Any]:
        """Return bound handlers for ``MeseexBox``."""
        return {
            "Preparing": self.prepare_request,
            "Load files": self.load_files,
            "Uploading files": self.upload_files,
            "Sending request": self.send_request,
            "Polling": self.poll_status,
            "Processing result": self.process_result,
        }

    async def prepare_request(self, job: APISeex) -> RequestData:
        stack = job.provider_stack
        return stack.api_client.format_request_params(job.endpoint, job.input)

    async def load_files(self, job: APISeex) -> RequestData:
        request_data = job.prev_task_output
        if request_data is None:
            raise ValueError("load_files: missing RequestData from Preparing")
        if not request_data.file_params:
            return request_data
        stack = job.provider_stack
        request_data.file_params = await stack.file_handler.load_files_from_disk(request_data.file_params)
        return request_data

    async def upload_files(self, job: APISeex) -> RequestData:
        request_data = job.prev_task_output
        if request_data is None:
            raise ValueError("upload_files: missing RequestData from prior pipeline task")
        if not request_data.file_params:
            return request_data
        stack = job.provider_stack
        request_data.file_params = await stack.file_handler.upload_files(request_data.file_params)
        return request_data

    async def send_request(self, job: APISeex) -> Any:
        request_data = job.prev_task_output
        if request_data is None:
            raise ValueError(
                "send_request: missing RequestData from prior pipeline task "
                "(Preparing / Load files / Uploading files)"
            )
        stack = job.provider_stack

        if isinstance(request_data.file_params, MediaDict) and request_data.file_params:
            if request_data.body_content_type == stack.api_client._JSON_BODY_CONTENT_TYPE:
                for name, value in request_data.file_params.items():
                    request_data.body_params[name] = stack.api_client._serialize_json_body_file_value(value)
                request_data.file_params = {}
            else:
                non_file_params = request_data.file_params.get_non_file_params(include_urls=True)
                if non_file_params:
                    request_data.body_params.update(non_file_params)

                file_model_fields, raw_files = stack.api_client.partition_media_for_multipart(
                    job.endpoint, request_data.file_params
                )
                if file_model_fields:
                    request_data.body_params.update(file_model_fields)
                request_data.file_params = raw_files
                request_data.file_params = await stack.file_handler.prepare_files_for_send(
                    request_data.file_params
                )
        elif request_data.file_params:
            request_data.file_params = await stack.file_handler.prepare_files_for_send(request_data.file_params)

        logger.info("send_request | Sending request to %s", request_data.url)
        timeout_hint = getattr(job.endpoint, "timeout_hint_s", None)
        timeout_s = float(timeout_hint) if timeout_hint else 60.0
        job_id = getattr(job, "name", None) or getattr(job, "meseex_id", None)
        profile_start(job_id)
        response = await stack.api_client.send_request(request_data, timeout_s=timeout_s)
        logger.info(
            "send_request | Received response: status=%d content_type=%s",
            response.status_code, response.headers.get("Content-Type"),
        )
        profile_event(
            "sdk",
            "provider_headers",
            job_id,
            status=response.status_code,
            content_type=(response.headers.get("Content-Type") or "").replace(" ", ""),
        )

        error = await stack.parser.check_response_status(response)
        if error:
            logger.error("send_request | Request failed: %s", error)
            raise Exception(error)

        parsed = await stack.parser.parse_response(response, materialize_media=job.materialize_media)

        if isinstance(parsed, StreamingResponse):
            logger.info("send_request | Detected direct stream response")
            job.direct_response = response
            job.runtime.refresh_stream_state()
            profile_event("sdk", "direct_stream", job_id)
        else:
            if not response.is_closed:
                await response.aclose()

        logger.info("send_request | Parsed response type: %s", type(parsed).__name__)
        return parsed

    @polling_task(poll_interval_seconds=1.0, timeout_seconds=3600)
    async def poll_status(self, job: APISeex) -> Any:
        parsed_response = job.prev_task_output

        if not isinstance(parsed_response, JOB_RESPONSE_TYPES):
            return parsed_response

        stack = job.provider_stack

        try:
            http_response = await stack.api_client.poll_status(parsed_response)
        except Exception as e:
            return retry_poll_or_raise(job, e)

        error = await stack.parser.check_response_status(http_response)
        if error:
            status_code = getattr(http_response, "status_code", 0)
            if not http_response.is_closed:
                await http_response.aclose()
            wrapped = ValueError(f"Job status polling failed: {error}")
            if status_code in TRANSIENT_POLL_HTTP_STATUSES:
                return retry_poll_or_raise(job, wrapped)
            raise wrapped

        job.set_task_data({"number_of_polling_errors": 0})
        parsed_response = await stack.parser.parse_response(http_response, parse_media=False)

        if not http_response.is_closed:
            await http_response.aclose()

        if not isinstance(parsed_response, JOB_RESPONSE_TYPES):
            raise ValueError(f"Expected job response but got {type(parsed_response)}")

        job.set_task_output(parsed_response)
        job.runtime.refresh_stream_state()

        status = stack.api_client.get_status(parsed_response)

        if status == APIJobStatus.FINISHED:
            return parsed_response
        if status == APIJobStatus.CANCELLED:
            job.mark_cancelled(cancel_result=parsed_response)
            job.runtime.refresh_stream_state()
            return parsed_response
        if status in (APIJobStatus.FAILED, APIJobStatus.REJECTED, APIJobStatus.TIMEOUT):
            err = getattr(parsed_response, "error", None)
            raise ValueError(err or f"Job failed with status: {getattr(parsed_response, 'status', 'unknown')}")

        progress = getattr(parsed_response, "progress", None)
        message = getattr(parsed_response, "message", None)
        raw_status = getattr(parsed_response, "status", "unknown")

        progress_msg = f"Job {getattr(parsed_response, 'id', getattr(parsed_response, 'job_id', '?'))}"
        progress_msg += f": {message}" if message else f" status: {raw_status}"

        job.set_task_progress(progress, progress_msg)
        return PollAgain(f"Job status: {raw_status}")

    async def process_result(self, job: APISeex) -> Any:
        response = job.prev_task_output
        stack = job.provider_stack

        if isinstance(response, StreamingResponse):
            return response

        if not isinstance(response, JOB_RESPONSE_TYPES):
            return stack.parser.parse_media(response, job.materialize_media)

        raw_result = stack.api_client.get_result(response)
        return stack.parser.parse_media(raw_result, job.materialize_media)
