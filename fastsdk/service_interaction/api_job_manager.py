from apipod_registry.schemas.service_definitions import (
    ServiceDefinition, ServiceAddress,
    RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress,
)
from apipod_registry.registry import Registry

from fastsdk.service_interaction.api_seex import APISeex
from fastsdk.service_interaction.job_runtime import JobRuntimePort
from meseex import MeseexBox
from meseex.control_flow import polling_task, PollAgain

from fastsdk.service_interaction.request.file_handler import FileHandler
from fastCloud import ReplicateUploadAPI

from fastsdk.service_interaction.response.response_parser import ResponseParser
from fastsdk.service_interaction.response.stream_session import StreamSession
from socaity_schemas import JOB_RESPONSE_TYPES, StreamingResponse

from fastsdk.service_interaction.request import (
    APIClient, APIClientReplicate, APIClientRunpod, APIClientSocaity, RequestData,
)
from fastsdk.service_interaction.request.api_client_runpod import APIClientRunpodApipod
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from media_toolkit import MediaDict, media_from_any

import logging
import time
from typing import Any, Dict


logger = logging.getLogger(__name__)


class ApiJobManager(JobRuntimePort):
    """Sole orchestrator for asynchronous API jobs.

    Owns the provider clients, parsers, file handlers, and the ``MeseexBox`` task
    pipeline. It is the only place that talks to the network and the kernel, and
    it implements ``JobRuntimePort`` so an ``APISeex`` handle can delegate its
    user-facing lifecycle methods here.
    """

    _CLIENT_CLASSES = {
        "runpod": APIClientRunpod,
        "runpod_apipod": APIClientRunpodApipod,
        "socaity": APIClientSocaity,
        "replicate": APIClientReplicate,
    }

    def __init__(self, service_registry: Registry, progress_verbosity: int = 2):
        self.service_registry = service_registry
        self.api_clients: Dict[str, APIClient] = {}
        self.file_handlers: Dict[str, FileHandler] = {}
        self._provider_types: Dict[str, str] = {}
        self._parser_cache: Dict[str, ResponseParser] = {}
        self.tasks = {
            "Preparing": self._prepare_request,
            "Load files": self._load_files,
            "Uploading files": self._upload_files,
            "Sending request": self._send_request,
            "Polling": self._poll_status,
            "Processing result": self._process_result,
        }
        self.meseex_box = MeseexBox(task_methods=self.tasks, progress_verbosity=progress_verbosity)

    # ------------------------------------------------------------------
    # Provider resolution & parser cache
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_service_type(service_def: ServiceDefinition) -> str:
        addr = service_def.service_address
        if isinstance(addr, RunpodServiceAddress):
            if service_def.specification in ("apipod", "socaity"):
                return "runpod_apipod"
            return "runpod"
        if isinstance(addr, SocaityServiceAddress):
            return "socaity"
        if isinstance(addr, ReplicateServiceAddress):
            return "replicate"
        if isinstance(addr, ServiceAddress):
            if service_def.specification in ("apipod", "socaity"):
                return "socaity"
            if service_def.specification == "runpod":
                return "runpod"
        return "other"

    def _get_parser(self, service_id: str) -> ResponseParser:
        provider = self._provider_types.get(service_id, "other")
        if provider not in self._parser_cache:
            self._parser_cache[provider] = ResponseParser(provider)
        return self._parser_cache[provider]

    # ------------------------------------------------------------------
    # Client / handler registration
    # ------------------------------------------------------------------

    def add_api_client(self, service_id: str, api_key: str):
        if service_id in self.api_clients:
            return

        service_def = self.service_registry.get_service(service_id)
        if not service_def:
            raise ValueError(f"Service {service_id} not found")
        if not hasattr(service_def, "service_address") or service_def.service_address is None:
            raise ValueError(
                f"Service {service_id} has no service address. "
                "Add one with Registry.update_service(service_id, service_address=...)"
            )

        service_type = self._determine_service_type(service_def)
        self._provider_types[service_id] = service_type

        client_cls = self._CLIENT_CLASSES.get(service_type, APIClient)
        self.api_clients[service_id] = client_cls(service_def=service_def, api_key=api_key)

    def add_file_handler(self, service_id: str, api_key: str = None, file_handler: FileHandler = None):
        if file_handler is not None:
            self.file_handlers[service_id] = file_handler
            return

        service_def = self.service_registry.get_service(service_id)
        service_type = self._determine_service_type(service_def)

        if service_type == "socaity":
            file_handler = FileHandler(file_format="httpx", upload_to_cloud_threshold_mb=0, max_upload_file_size_mb=300)
        elif service_type in ("runpod", "runpod_apipod"):
            file_handler = FileHandler(file_format="base64", max_upload_file_size_mb=300)
        elif service_type == "replicate":
            fast_cloud = ReplicateUploadAPI(api_key=api_key)
            file_handler = FileHandler(fast_cloud=fast_cloud, file_format="base64", upload_to_cloud_threshold_mb=0, max_upload_file_size_mb=300)
        else:
            file_handler = FileHandler()

        self.file_handlers[service_id] = file_handler

    def load_api_client(self, service_name_or_id: str, api_key: str = None):
        service_def = self.service_registry.get_service(service_name_or_id)
        if not service_def:
            raise ValueError(f"Service {service_name_or_id} not found")

        self.add_api_client(service_def.id, api_key)
        self.add_file_handler(service_def.id, api_key)
        return service_def

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    async def _prepare_request(self, job: APISeex) -> RequestData:
        api_client = self.api_clients[job.service_def.id]
        return api_client.format_request_params(job.endpoint_def, job.input)

    async def _load_files(self, job: APISeex) -> RequestData:
        request_data = job.prev_task_output
        if not request_data.file_params:
            return request_data
        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.load_files_from_disk(request_data.file_params)
        return request_data

    async def _upload_files(self, job: APISeex) -> RequestData:
        request_data = job.prev_task_output
        if not request_data.file_params:
            return request_data
        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.upload_files(request_data.file_params)
        return request_data

    async def _send_request(self, job: APISeex) -> Any:
        request_data = job.prev_task_output
        api_client = self.api_clients[job.service_def.id]
        parser = self._get_parser(job.service_def.id)

        if isinstance(request_data.file_params, MediaDict):
            non_file_params = request_data.file_params.get_non_file_params(include_urls=True)
            if non_file_params:
                request_data.body_params.update(non_file_params)

        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.prepare_files_for_send(request_data.file_params)

        logger.info("_send_request | Sending request to %s", request_data.url)
        response = await api_client.send_request(request_data)
        logger.info(
            "_send_request | Received response: status=%d content_type=%s",
            response.status_code, response.headers.get("Content-Type"),
        )

        error = await parser.check_response_status(response)
        if error:
            logger.error("_send_request | Request failed: %s", error)
            raise Exception(error)

        parsed = await parser.parse_response(response)

        if isinstance(parsed, StreamingResponse):
            logger.info("_send_request | Detected direct stream response")
            job.direct_response = response
        else:
            if not response.is_closed:
                await response.aclose()

        logger.info("_send_request | Parsed response type: %s", type(parsed).__name__)
        return parsed

    @polling_task(poll_interval_seconds=1.0, timeout_seconds=3600)
    async def _poll_status(self, job: APISeex) -> Any:
        parsed_response = job.prev_task_output

        if not isinstance(parsed_response, JOB_RESPONSE_TYPES):
            return parsed_response

        api_client = self.api_clients[job.service_def.id]
        parser = self._get_parser(job.service_def.id)

        try:
            http_response = await api_client.poll_status(parsed_response)
        except Exception as e:
            n_errors = job.get_task_data() or {}
            n_polling_errors = n_errors.get("number_of_polling_errors", 0) if isinstance(n_errors, dict) else 0
            if n_polling_errors > 3:
                raise e
            job.set_task_data({"number_of_polling_errors": n_polling_errors + 1})
            return PollAgain(f"Job status polling failed: {e}")

        error = await parser.check_response_status(http_response)
        if error:
            if not http_response.is_closed:
                await http_response.aclose()
            raise ValueError(f"Job status polling failed: {error}")

        parsed_response = await parser.parse_response(http_response, parse_media=False)

        if not http_response.is_closed:
            await http_response.aclose()

        if not isinstance(parsed_response, JOB_RESPONSE_TYPES):
            raise ValueError(f"Expected job response but got {type(parsed_response)}")

        status = api_client.get_status(parsed_response)

        if status == APIJobStatus.FINISHED:
            return parsed_response
        if status == APIJobStatus.CANCELLED:
            job.mark_cancelled(cancel_result=parsed_response)
            return parsed_response
        if status == APIJobStatus.FAILED:
            err = getattr(parsed_response, "error", None)
            raise ValueError(err or f"Job failed with status: {getattr(parsed_response, 'status', 'unknown')}")

        progress = getattr(parsed_response, "progress", None)
        message = getattr(parsed_response, "message", None)
        raw_status = getattr(parsed_response, "status", "unknown")

        progress_msg = f"Job {getattr(parsed_response, 'id', getattr(parsed_response, 'job_id', '?'))}"
        progress_msg += f": {message}" if message else f" status: {raw_status}"

        job.set_task_progress(progress, progress_msg)
        job.set_task_output(parsed_response)
        return PollAgain(f"Job status: {raw_status}")

    async def _process_result(self, job: APISeex) -> Any:
        response = job.prev_task_output

        if isinstance(response, StreamingResponse):
            return response

        if not isinstance(response, JOB_RESPONSE_TYPES):
            return response

        api_client = self.api_clients[job.service_def.id]
        parser = self._get_parser(job.service_def.id)

        raw_result = api_client.get_result(response)
        return parser.parse_media(raw_result)

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    def submit_job(self, service_id: str, endpoint_id: str, data: dict) -> APISeex:
        service_def = self.service_registry.get_service(service_id)
        if not service_def:
            raise ValueError(f"Service {service_id} not found")

        endpoint_def = self.service_registry.get_endpoint(service_id, endpoint_id)
        if not endpoint_def:
            raise ValueError(f"Endpoint {endpoint_id} not found in service {service_id}")

        task_list = ["Preparing"]
        for param in endpoint_def.parameters:
            definitions = getattr(param, "definition", None)
            if definitions is not None:
                defs = definitions if isinstance(definitions, list) else [definitions]
                if any(getattr(d, "format", None) in {"file", "image", "video", "audio"} for d in defs):
                    task_list.append("Load files")
                    break

        fh = self.file_handlers.get(service_id)
        if fh is not None and hasattr(fh, "fast_cloud") and fh.fast_cloud is not None:
            task_list.append("Uploading files")

        task_list.append("Sending request")

        if service_def.specification in ["apipod", "socaity", "runpod", "replicate"]:
            task_list.append("Polling")

        task_list.append("Processing result")

        seex_name = f"{service_def.display_name}.{endpoint_def.path}"

        job = APISeex(
            service_def=service_def,
            endpoint_def=endpoint_def,
            data=data,
            tasks=task_list,
            name=seex_name,
            runtime=self,
        )
        return self.meseex_box.summon_meseex(job)

    # ------------------------------------------------------------------
    # Async bridge
    # ------------------------------------------------------------------

    @property
    def _loop(self):
        """The asyncio loop that owns httpx responses created during tasks."""
        return self.meseex_box.task_executor.async_executor.loop

    def _run_async_call(self, method, *args, timeout_s: float = 30.0):
        """Bridge helper: run an async method synchronously via the task executor."""
        task = self.meseex_box.task_executor.submit(method, *args)
        started_at = time.monotonic()
        while not task.is_completed:
            if timeout_s is not None and (time.monotonic() - started_at) > timeout_s:
                task.cancel()
                raise TimeoutError("Timed out while waiting for async call")
            time.sleep(0.01)
        if task.error is not None:
            raise task.error
        return task.result

    # ------------------------------------------------------------------
    # JobRuntimePort: cancellation (single implementation)
    # ------------------------------------------------------------------

    @staticmethod
    def _local_cancel_response(job: APISeex, message: str) -> dict:
        return {"id": job.meseex_id, "status": "CANCELLED", "error": message}

    def _parse_cancel_response(self, parser: ResponseParser, http_response):
        error = self._run_async_call(parser.check_response_status, http_response)
        if error:
            if not http_response.is_closed:
                self._run_async_call(http_response.aclose)
            raise ValueError(f"Job cancellation failed: {error}")
        parsed = self._run_async_call(parser.parse_response, http_response, False)
        if not http_response.is_closed:
            self._run_async_call(http_response.aclose)
        return parsed if isinstance(parsed, JOB_RESPONSE_TYPES) else None

    def cancel(self, job: APISeex, wait: bool = False, timeout_s: float = 30.0, poll_interval_s: float = 0.5) -> Any:
        """Cancel a job remotely (provider permitting) and locally via the kernel.

        Adopts the wait-capable semantics: when ``wait`` is set, polls the remote
        until it confirms ``CANCELLED`` or reaches another terminal state, instead
        of optimistically assuming the cancel endpoint succeeded.
        """
        if job.is_terminal:
            return job.cancel_result or job.response

        api_client = self.api_clients.get(job.service_def.id)
        parser = self._get_parser(job.service_def.id)
        current_response = job.response

        has_cancel_url = (
            api_client is not None
            and isinstance(current_response, JOB_RESPONSE_TYPES)
            and api_client.get_cancel_url(current_response)
        )

        if not has_cancel_url:
            cancel_response = current_response or self._local_cancel_response(job, "Cancelled before remote job submission")
            self.meseex_box.cancel_meseex(job, cancel_result=cancel_response)
            return cancel_response

        try:
            http_response = self._run_async_call(api_client.cancel_job, current_response, timeout_s=timeout_s)
            cancel_response = self._parse_cancel_response(parser, http_response)
        except Exception as e:
            logger.warning("Remote cancellation for job %s failed: %s. Job will continue.", job.meseex_id, e)
            return current_response

        if cancel_response is None:
            job.set_cancel_result(current_response)
            return current_response

        status = api_client.get_status(cancel_response)

        if status == APIJobStatus.CANCELLED:
            self.meseex_box.cancel_meseex(job, cancel_result=cancel_response)
            return cancel_response

        if status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT}:
            job.set_cancel_result(cancel_response)
            return cancel_response

        job.set_cancel_result(cancel_response)
        if not wait:
            return cancel_response

        return self._wait_for_remote_cancellation(job, api_client, parser, cancel_response, timeout_s, poll_interval_s)

    def _wait_for_remote_cancellation(self, job, api_client, parser, cancel_response, timeout_s, poll_interval_s):
        current_response = cancel_response
        deadline = time.monotonic() + timeout_s

        while isinstance(current_response, JOB_RESPONSE_TYPES):
            status = api_client.get_status(current_response)

            if status == APIJobStatus.CANCELLED:
                self.meseex_box.cancel_meseex(job, cancel_result=current_response)
                return current_response

            if status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT}:
                job.set_cancel_result(current_response)
                return current_response

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                job.set_cancel_result(current_response)
                return current_response

            time.sleep(min(poll_interval_s, remaining))
            http_response = self._run_async_call(
                api_client.poll_status, current_response, timeout_s=min(remaining, 30.0)
            )
            next_response = self._parse_cancel_response(parser, http_response)
            if next_response is None:
                job.set_cancel_result(current_response)
                return current_response

            current_response = next_response

        return current_response

    # ------------------------------------------------------------------
    # JobRuntimePort: streaming
    # ------------------------------------------------------------------

    def _open_stream_session(self, job: APISeex, timeout_s: float = 60.0) -> StreamSession:
        """Resolve a live stream source and wrap it in a StreamSession.

        Prefers a ``direct_response`` (immediate SSE/raw stream) captured at send
        time; otherwise opens the provider ``links.stream`` URL once the poll loop
        exposes it. Blocks until a source is available or the job terminates.
        """
        deadline = time.monotonic() + timeout_s
        api_client = self.api_clients.get(job.service_def.id)

        while True:
            if job.direct_response is not None:
                return StreamSession(job.direct_response, self._loop)

            current = job.response
            if api_client is not None and isinstance(current, JOB_RESPONSE_TYPES) and api_client.get_stream_url(current):
                response = self._run_async_call(api_client.open_stream, current)
                return StreamSession(response, self._loop)

            if job.is_terminal or time.monotonic() > deadline:
                raise ValueError(f"Job {job.meseex_id} exposes no stream")

            time.sleep(0.05)

    def stream(self, job: APISeex, **kwargs) -> StreamSession:
        return self._open_stream_session(job)

    def astream(self, job: APISeex, **kwargs) -> StreamSession:
        # A StreamSession serves both sync (iter_*) and async (aiter_*) consumers.
        return self._open_stream_session(job)

    def assemble_result(self, job: APISeex) -> Any:
        """Drain a streaming job into one assembled result."""
        session = self._open_stream_session(job)
        if session.is_sse:
            return "".join(self._chunk_text(chunk) for chunk in session.iter_chunks())

        data = b"".join(session.iter_bytes())
        try:
            return media_from_any(data, allow_reads_from_disk=False)
        except Exception:
            return data

    @staticmethod
    def _chunk_text(chunk: Any) -> str:
        """Extract text from an OpenAI-style SSE chunk, or stringify it."""
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or choices[0].get("message") or {}
                return delta.get("content") or ""
        return str(chunk)
