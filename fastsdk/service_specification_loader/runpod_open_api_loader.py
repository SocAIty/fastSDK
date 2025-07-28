from fastsdk.fastClient import TemporaryFastClient
from fastsdk.service_definition import (
    ServiceDefinition, EndpointDefinition
)
from fastsdk.service_specification_loader.parsers.service_adress_parser import create_service_address
from typing import Any, Dict
import uuid

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fastsdk.service_interaction.api_job_manager import APISeex


class RunpodOpenAPILoader:
    """
    Simplified loader for fetching OpenAPI specifications from RunPod FastTaskAPI endpoints.
    Polls the service_definition from the runpod serverless fasttaskapi server and creates a temporary service definition.
    Uses ServiceManager and ApiJobManager infrastructure instead of implementing logic from scratch.
    """
    
    def __init__(self, runpod_url: str, api_key: str):
        self.runpod_url = runpod_url
        self.api_key = api_key

        # Create temporary service definition
        self.service_def = self._create_temp_service_definition()
        
        # Add service to manager and configure API client
        self.client = TemporaryFastClient(self.service_def, api_key=self.api_key)

    def _create_temp_service_definition(self) -> ServiceDefinition:
        """Create a temporary service definition for the RunPod OpenAPI endpoint"""
        # Create service address using existing parser
        service_address = create_service_address(self.runpod_url, "runpod")
        
        # Create endpoint definition for OpenAPI spec endpoint
        openapi_endpoint = EndpointDefinition(
            id="openapi.json",
            path="/openapi.json",  # Virtual path for our use case
            timeout_s=1800.0  # Reasonable timeout for OpenAPI spec requests
        )
        
        # Create temporary service definition
        service_def = ServiceDefinition(
            id=f"temp_runpod_openapi_{uuid.uuid4().hex[:8]}",
            display_name="Temp RunPod OpenAPI Loader",
            service_address=service_address,
            specification="runpod",
            endpoints=[openapi_endpoint],
            category=None,  # No specific category for temporary OpenAPI loader
            family_id=None  # No family association for temporary service
        )
        
        return service_def
        
    def load_openapi_spec_async(self) -> 'APISeex':
        """
        Load OpenAPI specification asynchronously using ApiJobManager.
        Returns a MrMeseex job that can be awaited for the result.
        """
        # Submit job through ApiJobManager with path parameter
        job = self.client.submit_job(endpoint_id="openapi.json")
        return job
    
    def load_openapi_spec(self) -> Dict[str, Any]:
        """
        Load OpenAPI specification synchronously.
        Returns the parsed OpenAPI specification as a dictionary.
        """
        job = self.load_openapi_spec_async()
        result = job.wait_for_result()
        return result
