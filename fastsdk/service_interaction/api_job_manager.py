import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from apipod_registry.definitions.service_definitions import (
    ServiceDefinition, ServiceAddress,
    RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress,
)
from apipod_registry.registry import Registry

from fastsdk.service_interaction.api_seex import APISeex
from meseex import MeseexBox
from meseex.control_flow import polling_task, PollAgain

from fastsdk.service_interaction.request.file_handler import FileHandler
from fastCloud import ReplicateUploadAPI

from fastsdk.service_interaction.response.response_parser import ResponseParser
from fastsdk.service_interaction.response.response_schemas import JOB_RESPONSE_TYPES, StreamingResponse

from fastsdk.service_interaction.request import (
    APIClient, APIClientReplicate, APIClientRunpod, APIClientSocaity, RequestData,
)
from fastsdk.service_interaction.request.api_client_runpod import APIClientRunpodApipod
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from media_toolkit import MediaDict


class ApiJobManager:
    """Manages the lifecycle of asynchronous API jobs by orchestrating services."""

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
            cancel_handler=self.cancel_api_job,
        )
        job._api_client = self.api_clients[service_id]
        job._response_parser = self._get_parser(service_id)

        return self.meseex_box.summon_meseex(job)

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

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

    def _try_remote_cancel(self, job: APISeex):
        """Best-effort: send a cancel request to the remote API."""
        current_response = job.response
        api_client = self.api_clients[job.service_def.id]

        if not isinstance(current_response, JOB_RESPONSE_TYPES) or not api_client.get_cancel_url(current_response):
            return None

        http_response = self._run_async_call(api_client.cancel_job, current_response)
        parser = self._get_parser(job.service_def.id)

        error = self._run_async_call(parser.check_response_status, http_response)
        if error:
            parsed_error = self._run_async_call(parser.parse_response, http_response, False)
            if not http_response.is_closed:
                self._run_async_call(http_response.aclose)
            if isinstance(parsed_error, JOB_RESPONSE_TYPES):
                return parsed_error
            raise ValueError(f"Remote cancellation failed with HTTP error: {error}")

        parsed = self._run_async_call(parser.parse_response, http_response, False)
        if not http_response.is_closed:
            self._run_async_call(http_response.aclose)
        return parsed if isinstance(parsed, JOB_RESPONSE_TYPES) else None

    def cancel_api_job(self, job: APISeex, **kwargs) -> Any:
        """Best-effort cancel: send remote cancel request if possible."""
        api_client = self.api_clients.get(job.service_def.id)
        current = job.response

        if not isinstance(current, JOB_RESPONSE_TYPES) or not api_client or not api_client.get_cancel_url(current):
            local_cancel = {"id": job.meseex_id, "status": "CANCELLED", "error": "Cancelled before remote submission"}
            self.meseex_box.cancel_meseex(job, cancel_result=local_cancel)
            return local_cancel

        try:
            remote_response = self._try_remote_cancel(job)
        except Exception as e:
            print(f"Warning: Remote cancellation for job {job.meseex_id} failed: {e}. Job will continue polling.")
            return current

        if remote_response is None:
            print(f"Warning: Job {job.meseex_id} has no remote cancel URL or no job response. Job will continue polling.")
            return current

        if api_client.get_status(remote_response) == APIJobStatus.CANCELLED:
            self.meseex_box.cancel_meseex(job, cancel_result=remote_response)
            return remote_response

        return remote_response
