from apipod_registry.schemas.service_definitions import (
    ServiceDefinition, ServiceAddress,
    RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress,
)
from apipod_registry.registry import Registry

from fastsdk.service_interaction.api_seex import APISeex
from fastsdk.service_interaction.job_runtime import JobRuntime
from fastsdk.service_interaction.async_bridge import AsyncBridge
from meseex import MeseexBox
from meseex.control_flow import polling_task, PollAgain

from fastsdk.service_interaction.request.file_handler import FileHandler
from fastCloud import ReplicateUploadAPI

from fastsdk.service_interaction.response.response_parser import ResponseParser
from socaity_schemas import JOB_RESPONSE_TYPES, StreamingResponse

from fastsdk.service_interaction.request import (
    APIClient, APIClientReplicate, APIClientRunpod, APIClientSocaity, RequestData,
)
from fastsdk.service_interaction.request.api_client_runpod import APIClientRunpodApipod
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from media_toolkit import MediaDict

import logging
from typing import Any, Dict


logger = logging.getLogger(__name__)


class ApiJobManager:
    """Process-level orchestrator and composition root for API jobs.

    Owns the provider clients, parsers, file handlers, and the ``MeseexBox`` task
    pipeline, and submits jobs into it. Each job's lifecycle (cancel, stream,
    assemble) is delegated to a per-job ``JobRuntime`` created at submit time, so
    transport ownership stays unambiguous: the manager wires and submits, the
    runtime controls one job, the ``APISeex`` handle stays a thin ticket.
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
        self._bridge = AsyncBridge(self.meseex_box.task_executor.async_executor)

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
            job.runtime.refresh_stream_state()
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

        job.set_task_output(parsed_response)
        job.runtime.refresh_stream_state()

        status = api_client.get_status(parsed_response)

        if status == APIJobStatus.FINISHED:
            return parsed_response
        if status == APIJobStatus.CANCELLED:
            job.mark_cancelled(cancel_result=parsed_response)
            job.runtime.refresh_stream_state()
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
        )
        job.runtime = JobRuntime(
            job=job,
            api_client=self.api_clients.get(service_id),
            parser=self._get_parser(service_id),
            meseex_box=self.meseex_box,
            bridge=self._bridge,
        )
        return self.meseex_box.summon_meseex(job)
