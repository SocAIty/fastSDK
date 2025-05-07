from typing import Any, Dict
from fastsdk.service_management import ServiceDefinition, EndpointDefinition
from fastsdk.service_management import ServiceAddress, RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress

from fastsdk.service_management import ServiceManager
from meseex import MeseexBox, MrMeseex
from meseex.control_flow import polling_task, PollAgain

from fastsdk.service_interaction.request.file_handler import FileHandler
from fastCloud import SocaityUploadAPI, ReplicateUploadAPI

from fastsdk.service_interaction.response.response_parser import ResponseParser
from fastsdk.service_interaction.response.base_response import BaseJobResponse

from fastsdk.service_interaction.request import APIClient, APIClientReplicate, APIClientRunpod, APIClientSocaity, RequestData
from fastsdk.service_interaction.response.api_job_status import APIJobStatus


class APISeex(MrMeseex):
    """Meseex extension specifically for API job handling"""
    def __init__(self, service_def: ServiceDefinition, endpoint_def: EndpointDefinition, data: Any = None, name: str = None, tasks: list = None):
        super().__init__(tasks, data, name)
        self.service_def = service_def
        self.endpoint_def = endpoint_def

    @property
    def response(self) -> BaseJobResponse:
        """
        Returns the latest parsed response from the API.
        """
        resp = self.get_task_output("Polling")
        if resp is not None:
            return resp
        return self.get_task_output("Sending request")


class _ApiJobManager:
    """
    Manages the lifecycle of asynchronous API jobs by orchestrating services.
    Delegates implementation details
    """
    def __init__(self):
        # ToDo: find correct place or building pattern for this.. (bild on demand.)
        # One method would be to store really all settings in the APISeex instance; and then derive from there
        self.api_clients: Dict[str, APIClient] = {}  # dict of service_id -> APIClient
        self.file_handlers: Dict[str, FileHandler] = {}  # dict of service_id -> FileHandler
        self.response_parser = ResponseParser()
        # Define task sequence
        self.tasks = {
            "Preparing": self._prepare_request,
            "Load files": self._load_files,
            "Uploading files": self._upload_files,
            "Sending request": self._send_request,
            "Polling": self._poll_status,
            "Processing result": self._process_result
        }

        # Create Meseex task orchestrator
        self.meseex_box = MeseexBox(task_methods=self.tasks)

    def add_api_client(self, service_id: str, api_key: str):
        if service_id not in self.api_clients:
            service_def = ServiceManager.get_service(service_id)
            if not service_def:
                raise ValueError(f"Service {service_id} not found")
            
            api_client = None
            if isinstance(service_def.service_address, RunpodServiceAddress):
                api_client = APIClientRunpod(service_def=service_def, api_key=api_key)
            elif isinstance(service_def.service_address, SocaityServiceAddress):
                api_client = APIClientSocaity(service_def=service_def, api_key=api_key)
            elif isinstance(service_def.service_address, ReplicateServiceAddress):
                api_client = APIClientReplicate(service_def=service_def, api_key=api_key)
            elif isinstance(service_def.service_address, ServiceAddress) and service_def.specification == "fasttaskapi":
                api_client = APIClientSocaity(service_def=service_def, api_key=api_key)
            else:
                api_client = APIClient(service_def=service_def, api_key=api_key)

            self.api_clients[service_id] = api_client

    def add_file_handler(self, service_id: str, file_handler: FileHandler = None):
        """
        Adds a file handler to the job manager.
        If no file handler is provided, the job manager will create a default one based on the service definition.
        """
        if file_handler is not None:
            self.file_handlers[service_id] = file_handler

        service_def = ServiceManager.get_service(service_id)
        if isinstance(service_def.service_address, RunpodServiceAddress):
            file_handler = FileHandler(file_format="base64", max_upload_file_size_mb=300)
        elif isinstance(service_def.service_address, SocaityServiceAddress):
            fast_cloud = SocaityUploadAPI(api_key=service_def.api_key)
            file_handler = FileHandler(fast_cloud=fast_cloud, file_format="httpx", upload_to_cloud_threshold_mb=3, max_upload_file_size_mb=3000)
        elif isinstance(service_def.service_address, ReplicateServiceAddress):
            fast_cloud = ReplicateUploadAPI(api_key=service_def.api_key)
            file_handler = FileHandler(fast_cloud=fast_cloud, file_format="base64", upload_to_cloud_threshold_mb=10, max_upload_file_size_mb=300)
        else:
            file_handler = FileHandler()

        self.file_handlers[service_id] = file_handler
    
    async def _prepare_request(self, job: APISeex) -> RequestData:
        api_client = self.api_clients[job.service_def.id]
        return api_client.format_request_params(job.endpoint_def, job.input)
     
    async def _load_files(self, job: APISeex) -> APISeex:
        """Task method that loads files from disk by delegating to FileHandler"""
        request_data = job.prev_task_output
        if not request_data.file_params or len(request_data.file_params) == 0:
            return request_data
        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.load_files_from_disk(request_data.file_params)
        return request_data
    
    async def _upload_files(self, job: APISeex) -> APISeex:
        """Task method that handles file upload by delegating to FileService"""

        request_data = job.prev_task_output
        if not request_data.file_params or len(request_data.file_params) == 0:
            return request_data

        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.upload_files(request_data.file_params)

        return request_data

    async def _send_request(self, job: APISeex) -> Any:
        """Task method that sends the request by delegating to ApiService"""
        request_data = job.prev_task_output
        api_client = self.api_clients[job.service_def.id]

        url_files = request_data.file_params.get_url_files()
        if url_files:
            request_data.body_params.update(url_files)

        fh = self.file_handlers.get(job.service_def.id)
        request_data.file_params = await fh.prepare_files_for_send(request_data.file_params)

        response = await api_client.send_request(request_data)

        # Check for HTTP errors
        error = self.response_parser.check_response_status(response)
        if error:
            raise ValueError(f"API request failed: {error}")
            
        # Parse the response
        parsed_response = self.response_parser.parse_response(response)
        
        return parsed_response

    @polling_task(poll_interval_seconds=1.0, timeout_seconds=300)
    async def _poll_status(self, job: APISeex) -> Any:
        """Task method that polls for job completion by delegating to ApiService"""
        parsed_response = job.prev_task_output

        # If not a job-based API response, skip polling
        if not isinstance(parsed_response, BaseJobResponse):
            return parsed_response

        api_client = self.api_clients[job.service_def.id]
        http_response = await api_client.poll_status(parsed_response)

        # Check for HTTP errors
        error = self.response_parser.check_response_status(http_response)
        if error:
            raise ValueError(f"Job status polling failed: {error}")
            
        # Parse the response
        parsed_response = self.response_parser.parse_response(http_response, parse_media=False)
        
        if not isinstance(parsed_response, BaseJobResponse):
            raise ValueError(f"Expected job response but got {type(parsed_response)}")
            
        # Return result if job is done, otherwise signal to poll again
        if parsed_response.status == APIJobStatus.FINISHED:
            return parsed_response
        elif parsed_response.status in [APIJobStatus.FAILED, APIJobStatus.CANCELLED]:
            raise ValueError(parsed_response.error or f"Job failed with status: {parsed_response.status.name}")
 
        # Update progress based on job status
        if isinstance(parsed_response, BaseJobResponse): 
            if parsed_response.progress is None:
                job.set_task_progress(
                    None,
                    f"Job {parsed_response.id} status: {parsed_response.status.name}"
                )
            else:
                message = f"Job {parsed_response.id}"
                if parsed_response.progress.message:
                    message += f": {parsed_response.progress.message}"
                else:
                    message += f" status: {parsed_response.status.name}"
                
                job.set_task_progress(
                    parsed_response.progress.progress,
                    message
                )

        return PollAgain(f"Job status: {parsed_response.status.name}")

    async def _process_result(self, job: APISeex) -> Any:
        """Task method that processes the result by delegating to FileService"""

        result = job.prev_task_output
        if isinstance(result, BaseJobResponse):
            result = result.result
            
        # Process file responses
        fh = self.file_handlers.get(job.service_def.id)
        processed_result = await fh.process_file_response(result)
        
        return processed_result

    def submit_job(self, service_id: str, endpoint_id: str, data: dict) -> MrMeseex:
        """
        Submit a job for execution with the specified service and endpoint.
        Entry point for API interaction.
        Builds a blueprint for how the job needs to be executed with all necessary tasks.
        
        Args:
            service_id: ID of the service to use
            endpoint_id: ID of the endpoint to call
            params: Parameters for the API call
            
        Returns:
            MrMeseex task that can be awaited for the result
        """
        # Get service and endpoint definitions
        service_def = ServiceManager.get_service(service_id)
        if not service_def:
            raise ValueError(f"Service {service_id} not found")

        endpoint_def = ServiceManager.get_endpoint(service_id, endpoint_id)
        if not endpoint_def:
            raise ValueError(f"Endpoint {endpoint_id} not found in service {service_id}")

        # Build task list
        task_list = ["Preparing"]
        for param in endpoint_def.parameters:
            param_types = param.type if isinstance(param.type, list) else [param.type]
            if any(t in ["file", "image", "video", "audio"] for t in param_types):
                task_list.append("Load files")
                break

        fh = self.file_handlers.get(service_id)
        if fh is not None and hasattr(fh, "fast_cloud") and fh.fast_cloud is not None:
            task_list.append("Uploading files")

        task_list.append("Sending request")

        if service_def.specification in ["fasttaskapi", "socaity", "runpod", "replicate"]:
            task_list.append("Polling")

        # FastTaskAPI sollte aufgemotzt werden, damit beim Request Result bereits klar ist, ob es ein FileResult werden wird..?
        # Vorerst kann man einfach immer den Schritt 'process result' ausführen.
        # for response in endpoint_def.responses:
        #    if response.type in ["file", "image", "video", "audio"]:
        #        request_blueprint.has_download_files = True
        #        break

        task_list.append("Processing result")

        # Create job name
        seex_name = f"{service_def.display_name}.{endpoint_def.path}"
        
        # Create the job with the appropriate task list
        job = APISeex(
            service_def=service_def,
            endpoint_def=endpoint_def,
            data=data,
            tasks=task_list,
            name=seex_name
        )
        
        # Submit the job to the MeseexBox for execution
        return self.meseex_box.summon_meseex(job)


ApiJobManager = _ApiJobManager()
