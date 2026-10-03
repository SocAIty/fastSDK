"""Meseex task implementations for the API job pipeline."""

import logging
from typing import Any, Dict, Optional

from meseex.control_flow import polling_task, PollAgain
from socaity_schemas.public.providers import (
    JOB_RESPONSE_TYPES,
    SocaityJobResponse,
    StreamingResponse,
)
from media_toolkit import MediaDict

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

    Polling is ``GET /status`` only. When the next task is ``Streaming`` and
    ``links.stream`` appears, Polling returns so Streaming can own ``GET /stream``.
    Streaming is a pass-through when the envelope has no stream URL.
    """

    def as_task_map(self) -> Dict[str, Any]:
        """Return bound handlers for ``MeseexBox``."""
        return {
            "Preparing": self.prepare_request,
            "Load files": self.load_files,
            "Uploading files": self.upload_files,
            "Sending request": self.send_request,
            "Attach": self.attach_job,
            "Polling": self.poll_status,
            "Streaming": self.follow_stream,
            "Processing result": self.process_result,
        }

    async def attach_job(self, job: APISeex) -> Any:
        """Seed polling from an existing job envelope (``track_job``)."""
        envelope = job.input
        if isinstance(envelope, JOB_RESPONSE_TYPES):
            attached = envelope
        elif isinstance(envelope, dict):
            attached = SocaityJobResponse.model_validate(envelope)
        else:
            raise ValueError("Attach requires a job envelope (dict or SocaityJobResponse)")
        return attached

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
        response = await stack.api_client.send_request(request_data, timeout_s=timeout_s)
        logger.info(
            "send_request | Received response: status=%d content_type=%s",
            response.status_code, response.headers.get("Content-Type"),
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

        done = self._apply_status_envelope(job, stack, parsed_response)
        if done is not None:
            return done

        tasks = job.tasks or []
        nxt = job.current_task_index + 1
        if (
            nxt < len(tasks)
            and tasks[nxt] == "Streaming"
            and stack.api_client.get_stream_url(parsed_response)
        ):
            return parsed_response

        raw_status = getattr(parsed_response, "status", "unknown")
        return PollAgain(f"Job status: {raw_status}")

    def _apply_status_envelope(self, job: APISeex, stack, envelope: Any) -> Optional[Any]:
        """Apply a status snapshot. Return the envelope when terminal, else None."""
        job.set_task_output(envelope)
        job.runtime.refresh_stream_state()

        status = stack.api_client.get_status(envelope)
        if status == APIJobStatus.FINISHED:
            return envelope
        if status == APIJobStatus.CANCELLED:
            job.mark_cancelled(cancel_result=envelope)
            job.runtime.refresh_stream_state()
            return envelope
        if status in (APIJobStatus.FAILED, APIJobStatus.REJECTED, APIJobStatus.TIMEOUT):
            err = getattr(envelope, "error", None)
            raise ValueError(err or f"Job failed with status: {getattr(envelope, 'status', 'unknown')}")

        progress = getattr(envelope, "progress", None)
        message = getattr(envelope, "message", None)
        raw_status = getattr(envelope, "status", "unknown")
        progress_msg = f"Job {getattr(envelope, 'id', getattr(envelope, 'job_id', '?'))}"
        progress_msg += f": {message}" if message else f" status: {raw_status}"
        job.set_task_progress(progress, progress_msg)
        return None

    async def follow_stream(self, job: APISeex) -> Any:
        """Follow ``GET /stream`` until a terminal job frame.

        Pass-through when Polling already finished or the envelope has no stream URL.
        """
        envelope = job.prev_task_output
        if not isinstance(envelope, JOB_RESPONSE_TYPES):
            return envelope
        stack = job.provider_stack
        done = self._apply_status_envelope(job, stack, envelope)
        if done is not None:
            return done
        if not stack.api_client.get_stream_url(envelope):
            return envelope

        async for next_envelope in job.runtime.follow_status_stream(envelope):
            done = self._apply_status_envelope(job, stack, next_envelope)
            if done is not None:
                return done
        raise ValueError("Job status stream ended before a terminal status")

    async def process_result(self, job: APISeex) -> Any:
        response = job.prev_task_output
        stack = job.provider_stack

        if isinstance(response, StreamingResponse):
            return response

        if not isinstance(response, JOB_RESPONSE_TYPES):
            return stack.parser.parse_media(response, job.materialize_media)

        raw_result = stack.api_client.get_result(response)
        return stack.parser.parse_media(raw_result, job.materialize_media)
