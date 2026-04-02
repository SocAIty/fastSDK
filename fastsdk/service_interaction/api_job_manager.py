import logging
import time
from typing import Any, Dict, Optional, Callable, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

from apipod_registry.definitions.service_definitions import ServiceDefinition, EndpointDefinition, ServiceAddress, RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress, ServiceSpecification
from apipod_registry.registry import Registry

from fastsdk.service_interaction.api_seex import APISeex
from meseex import MeseexBox, MrMeseex
from meseex.control_flow import polling_task, PollAgain

from fastsdk.service_interaction.request.file_handler import FileHandler
from fastCloud import ReplicateUploadAPI

from fastsdk.service_interaction.response.response_parser import ResponseParser
from fastsdk.service_interaction.response.base_response import BaseJobResponse

from fastsdk.service_interaction.request import APIClient, APIClientReplicate, APIClientRunpod, APIClientSocaity, RequestData
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from media_toolkit import MediaDict


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
    
    @property
    def runtime_info(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Returns (delay_seconds, execution_seconds) in seconds.
        Normalizes different provider formats to a consistent float-based second unit.
        """
        delay_seconds: Optional[float] = None
        execution_seconds: Optional[float] = None
        
        resp = self.response
        if not resp:
            return None, None

        addr = self.service_def.service_address

        # --- Provider 1: Runpod ---
        if isinstance(addr, RunpodServiceAddress):
            delay_ms = getattr(resp, "delayTime", None)
            execution_ms = getattr(resp, "executionTime", None)

            if delay_ms is not None:
                delay_seconds = float(delay_ms) / 1000.0
            if execution_ms is not None:
                execution_seconds = float(execution_ms) / 1000.0

        # --- Provider 2: Replicate ---
        elif isinstance(addr, ReplicateServiceAddress):
            created_str = getattr(resp, "created_at", None)
            started_str = getattr(resp, "execution_started_at", None)

            if created_str and started_str:
                try:
                    # Parse ISO strings; handle 'Z' for UTC compatibility
                    t1 = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(str(started_str).replace("Z", "+00:00"))
                    delay_seconds = (t2 - t1).total_seconds()
                except (ValueError, TypeError):
                    delay_seconds = None

            # Normalize Replicate's ms to seconds
            exec_ms = getattr(resp, "execution_time_ms", None)
            if exec_ms is not None:
                execution_seconds = float(exec_ms) / 1000.0

        return delay_seconds, execution_seconds

class ApiJobManager:
    """
    Manages the lifecycle of asynchronous API jobs by orchestrating services.
    Delegates implementation details.
    """
    def __init__(self, service_registry: Registry, progress_verbosity: int = 2):
        self.service_registry = service_registry
        self.api_clients: Dict[str, APIClient] = {}
        self.file_handlers: Dict[str, FileHandler] = {}
        self.response_parser = ResponseParser()
        self.tasks = {
            "Preparing": self._prepare_request,
            "Load files": self._load_files,
            "Uploading files": self._upload_files,
            "Sending request": self._send_request,
            "Polling": self._poll_status,
            "Processing result": self._process_result
        }
        self.meseex_box = MeseexBox(task_methods=self.tasks, progress_verbosity=progress_verbosity)

    def _determine_service_type(self, service_def: ServiceDefinition) -> ServiceSpecification:
        if isinstance(service_def.service_address, RunpodServiceAddress):
            return "runpod"
        elif isinstance(service_def.service_address, SocaityServiceAddress):
            return "socaity"
        elif isinstance(service_def.service_address, ReplicateServiceAddress):
            return "replicate"
        elif isinstance(service_def.service_address, ServiceAddress):
            if service_def.specification in ("apipod", "socaity"):
                return "socaity"
            elif service_def.specification == "runpod":
                return "runpod"

        return "other"

    def add_api_client(self, service_id: str, api_key: str):
        if service_id not in self.api_clients:
            service_def = self.service_registry.get_service(service_id)
            if not service_def:
                raise ValueError(f"Service {service_id} not found")

            if not hasattr(service_def, "service_address") or service_def.service_address is None:
                raise ValueError(f"Service {service_id} has no service address. Add a service address to the service definition first with Registry.update_service(service_id, service_address=...)")

            service_type = self._determine_service_type(service_def)
            client_cls = {
                "runpod": APIClientRunpod,
                "socaity": APIClientSocaity,
                "replicate": APIClientReplicate,
            }.get(service_type, APIClient)

            self.api_clients[service_id] = client_cls(service_def=service_def, api_key=api_key)

    def add_file_handler(self, service_id: str, api_key: str = None, file_handler: FileHandler = None):
        if file_handler is not None:
            self.file_handlers[service_id] = file_handler
            return

        service_def = self.service_registry.get_service(service_id)
        service_type = self._determine_service_type(service_def)

        if service_type == "socaity":
            file_handler = FileHandler(file_format="httpx", upload_to_cloud_threshold_mb=0, max_upload_file_size_mb=300)
        elif service_type == "runpod":
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

        if isinstance(request_data.file_params, MediaDict):
            non_file_params = request_data.file_params.get_non_file_params(include_urls=True)
            if non_file_params:
                request_data.body_params.update(non_file_params)

        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.prepare_files_for_send(request_data.file_params)
        
        logger.info("_send_request | Sending request to %s", request_data.url)
        response = await api_client.send_request(request_data)
        
        logger.info("_send_request | Received response: status=%d content_type=%s", 
                    response.status_code, response.headers.get("Content-Type"))

        error = await self.response_parser.check_response_status(response)
        if error:
            logger.error("_send_request | Request failed: %s", error)
            raise Exception(error)

        parsed = await self.response_parser.parse_response(response)
        
        # If it's a direct stream, store the raw response on the job for the forwarder
        if isinstance(parsed, BaseJobResponse) and parsed.status == APIJobStatus.STREAMING:
            logger.info("_send_request | Detected direct stream response")
            job.direct_response = response
        else:
            # If not streaming, ensure response is closed after reading
            if not response.is_closed:
                await response.aclose()

        logger.info("_send_request | Parsed response type: %s", type(parsed).__name__)
        return parsed

    @polling_task(poll_interval_seconds=1.0, timeout_seconds=3600)
    async def _poll_status(self, job: APISeex) -> Any:
        parsed_response = job.prev_task_output

        if not isinstance(parsed_response, BaseJobResponse):
            return parsed_response

        # Streaming responses are terminal from the SDK's perspective.
        # The worker's override handles forwarding chunks to Redis.
        if parsed_response.status == APIJobStatus.STREAMING:
            return parsed_response

        api_client = self.api_clients[job.service_def.id]

        try:
            http_response = await api_client.poll_status(parsed_response)
        except Exception as e:
            n_errors = job.get_task_data() or {}
            n_polling_errors = n_errors.get("number_of_polling_errors", 0) if isinstance(n_errors, dict) else 0

            if n_polling_errors > 3:
                raise e
            job.set_task_data({"number_of_polling_errors": n_polling_errors + 1})
            return PollAgain(f"Job status polling failed: {e}")

        error = await self.response_parser.check_response_status(http_response)
        if error:
            if not http_response.is_closed:
                await http_response.aclose()
            raise ValueError(f"Job status polling failed: {error}")

        parsed_response = await self.response_parser.parse_response(http_response, parse_media=False)
        
        # Ensure response is closed after reading
        if not http_response.is_closed:
            await http_response.aclose()

        if not isinstance(parsed_response, BaseJobResponse):
            raise ValueError(f"Expected job response but got {type(parsed_response)}")

        if parsed_response.status == APIJobStatus.FINISHED:
            return parsed_response
        elif parsed_response.status == APIJobStatus.CANCELLED:
            job.mark_cancelled(cancel_result=parsed_response)
            return parsed_response
        elif parsed_response.status == APIJobStatus.FAILED:
            raise ValueError(parsed_response.error or f"Job failed with status: {parsed_response.status.value}")

        progress_msg = f"Job {parsed_response.id}"
        message = getattr(parsed_response, "message", None)
        if message:
            progress_msg += f": {message}"
        else:
            progress_msg += f" status: {parsed_response.status.value}"

        job.set_task_progress(parsed_response.progress, progress_msg)
        job.set_task_output(parsed_response)
        return PollAgain(f"Job status: {parsed_response.status.value}")

    async def _process_result(self, job: APISeex) -> Any:
        result = job.prev_task_output
        if not isinstance(result, BaseJobResponse):
            return result

        # Streaming responses have no result body to parse — the
        # actual tokens were forwarded to the StreamStore by the
        # worker's _poll_status override.  Return a marker so the
        # worker's _process_result knows the job was a stream.
        if result.status == APIJobStatus.STREAMING:
            return result

        result = await self.response_parser.parse_media_result(result)
        if result is None:
            return result

        return result.result

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
            cancel_handler=self.cancel_api_job
        )

        return self.meseex_box.summon_meseex(job)

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

    def _try_remote_cancel(self, job: APISeex) -> Optional[BaseJobResponse]:
        """Best-effort: send a cancel request to the remote API."""
        current_response = job.response
        if not isinstance(current_response, BaseJobResponse) or not current_response.cancel_job_url:
            return None

        http_response = self._run_async_call(
            self.api_clients[job.service_def.id].cancel_job,
            current_response,
        )
        error = self._run_async_call(self.response_parser.check_response_status, http_response)
        if error:
            parsed_error = self._run_async_call(self.response_parser.parse_response, http_response, False)
            if not http_response.is_closed:
                self._run_async_call(http_response.aclose)
            if isinstance(parsed_error, BaseJobResponse):
                return parsed_error
            raise ValueError(f"Remote cancellation failed with HTTP error: {error}")

        parsed = self._run_async_call(self.response_parser.parse_response, http_response, False)
        if not http_response.is_closed:
            self._run_async_call(http_response.aclose)
        return parsed if isinstance(parsed, BaseJobResponse) else None

    def cancel_api_job(self, job: APISeex, **kwargs) -> Any:
        """Best-effort cancel: send remote cancel request if possible."""
        if not isinstance(job.response, BaseJobResponse) or not job.response.cancel_job_url:
            local_cancel = BaseJobResponse(
                id=job.meseex_id,
                status=APIJobStatus.CANCELLED,
                error="Cancelled before remote submission",
                service_specification=job.service_def.specification,
            )
            self.meseex_box.cancel_meseex(job, cancel_result=local_cancel)
            return local_cancel

        try:
            remote_response = self._try_remote_cancel(job)
        except Exception as e:
            print(f"Warning: Remote cancellation for job {job.meseex_id} failed: {e}. Job will continue polling.")
            return job.response

        if remote_response is None:
            print(f"Warning: Job {job.meseex_id} has no remote cancel URL or no job response. Job will continue polling.")
            return job.response

        if remote_response.status == APIJobStatus.CANCELLED:
            self.meseex_box.cancel_meseex(job, cancel_result=remote_response)
            return remote_response

        return remote_response
