from apipod_registry import create_service
from apipod_registry.registry import Registry
from socaity_schemas import JobLinks, SocaityJobResponse
from socaity_schemas.contract import Endpoint, ServiceContract
from socaity_schemas.contract.address import SocaityServiceAddress

from fastsdk.service_interaction.api_seex import APISeex
from fastsdk.service_interaction.job_runtime import JobRuntime
from fastsdk.service_interaction.async_bridge import AsyncBridge
from fastsdk.service_interaction.provider_stack_registry import ProviderStackRegistry
from fastsdk.service_interaction.pipeline_planner import PipelinePlanner
from fastsdk.service_interaction.job_tasks import JobTasks
from meseex import MeseexBox

_GATEWAY_PREFIX = "_socaity_gateway"


def _gateway_service(origin: str):
    """Minimal AIService for a gateway origin. Not a catalog row."""
    origin = origin.rstrip("/")
    contract = ServiceContract(
        title="Socaity gateway",
        specification="apipod",
        has_job_queue=True,
        endpoints=[],
    )
    return create_service(
        contract,
        address=SocaityServiceAddress(base_url=origin, path=""),
        provider="socaity",
        service_id=f"{_GATEWAY_PREFIX}:{origin}",
        name="socaity_gateway",
    )


def _factory_endpoint(path: str) -> Endpoint:
    normalized = path if path.startswith("/") else f"/{path}"
    return Endpoint(
        path=normalized,
        method="POST",
        request_body_content_type="application/json",
        supports_streaming=True,
    )


class ApiJobManager:
    """Process-level orchestrator and composition root for API jobs.

    Wires ``MeseexBox`` task handlers, submits jobs, and attaches a per-job
    ``JobRuntime``. Provider stack loading lives in ``ProviderStackRegistry``;
    task implementations live in ``JobTasks``; task order is chosen by
    ``PipelinePlanner``.
    """

    def __init__(
        self,
        service_registry: Registry,
        stacks: ProviderStackRegistry,
        progress_verbosity: int = 2,
    ):
        self.service_registry = service_registry
        self.stacks = stacks
        self._job_tasks = JobTasks()
        self.meseex_box = MeseexBox(
            task_methods=self._job_tasks.as_task_map(),
            progress_verbosity=progress_verbosity,
        )
        self._bridge = AsyncBridge(self.meseex_box.task_executor.async_executor)

    def submit_job(
        self,
        service_id: str,
        endpoint_id: str,
        data: dict,
        api_key: str = None,
        materialize_media: bool = True,
    ) -> APISeex:
        service = self.service_registry.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")

        endpoint = self.service_registry.get_endpoint(service_id, endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint {endpoint_id} not found in service {service_id}")

        stack = self.stacks.ensure(service_id, api_key)
        tasks = PipelinePlanner.plan(service, endpoint, stack)
        seex_name = f"{service.display_name}.{endpoint.path}"

        job = APISeex(
            service=service,
            endpoint=endpoint,
            data=data,
            tasks=tasks,
            name=seex_name,
            stack=stack,
            materialize_media=materialize_media,
        )
        return self._wire(job, stack)

    def _wire(self, job: APISeex, stack) -> APISeex:
        job.runtime = JobRuntime(
            job=job,
            api_client=stack.api_client,
            parser=stack.parser,
            meseex_box=self.meseex_box,
            bridge=self._bridge,
        )
        return self.meseex_box.summon_meseex(job)

    def submit_factory(
        self,
        path: str,
        data: dict,
        *,
        address: str,
        api_key: str = None,
        materialize_media: bool = True,
    ) -> APISeex:
        """Submit a job to a gateway factory path (no catalog service).

        Same poll, cancel, and stream runtime as ``submit_job``.
        ``path`` is rooted at ``address``, e.g. ``/v1/workflows/{id}/run``.
        """
        service = _gateway_service(address)
        endpoint = _factory_endpoint(path)
        stack = self.stacks.ensure_for(service, api_key)
        tasks = PipelinePlanner.plan(service, endpoint, stack)
        job = APISeex(
            service=service,
            endpoint=endpoint,
            data=data or {},
            tasks=tasks,
            name=path,
            stack=stack,
            materialize_media=materialize_media,
        )
        return self._wire(job, stack)

    def track_job(
        self,
        job_id: str,
        *,
        address: str,
        api_key: str = None,
        materialize_media: bool = True,
    ) -> APISeex:
        """Re-attach to a running gateway job and poll until it is terminal."""
        service = _gateway_service(address)
        endpoint = _factory_endpoint(f"/status/{job_id}")
        stack = self.stacks.ensure_for(service, api_key)
        envelope = SocaityJobResponse(
            job_id=job_id,
            status="queued",
            links=JobLinks(
                status=f"/status/{job_id}",
                cancel=f"/cancel/{job_id}",
                stream=f"/stream/{job_id}",
            ),
        )
        job = APISeex(
            service=service,
            endpoint=endpoint,
            data=envelope,
            tasks=["Attach", "Polling", "Processing result"],
            name=f"track:{job_id}",
            stack=stack,
            materialize_media=materialize_media,
        )
        return self._wire(job, stack)
