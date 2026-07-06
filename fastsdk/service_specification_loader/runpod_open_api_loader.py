from fastsdk.fastClient import FastClient
from apipod_registry import create_service
from socaity_schemas.contract import Endpoint, ServiceContract
from socaity_schemas.platform import AIService
from typing import Any, Dict
import uuid

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fastsdk.service_interaction.api_seex import APISeex


class RunpodOpenAPILoader:
    """
    Simplified loader for fetching OpenAPI specifications from RunPod APIPod endpoints.
    Fetches the openapi spec through a RunPod serverless job using a temporary AIService.
    Uses Registry and ApiJobManager infrastructure instead of implementing logic from scratch.
    """

    def __init__(self, runpod_url: str, api_key: str):
        self.runpod_url = runpod_url
        self.api_key = api_key

        # Create temporary service
        self.service = self._create_temp_service()

        # Add service to manager and configure API client
        self.client = FastClient(self.service, api_key=self.api_key, temporary=True)

    def _create_temp_service(self) -> AIService:
        """Create a temporary AIService whose only endpoint fetches /openapi.json through the runtime."""
        contract = ServiceContract(
            title="Temp RunPod OpenAPI Loader",
            specification="openapi",
            has_job_queue=True,  # RunPod serverless answers /run with a job envelope
            endpoints=[
                Endpoint(
                    path="/openapi.json",  # Virtual path routed through the RunPod job body
                    method="POST",
                    operation_id="openapi.json",
                    timeout_hint_s=1800.0,
                )
            ],
        )
        return create_service(
            contract,
            address=self.runpod_url,
            provider="runpod",
            service_id=f"temp_runpod_openapi_{uuid.uuid4().hex[:8]}",
        )

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
