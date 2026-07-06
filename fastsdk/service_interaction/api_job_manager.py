from apipod_registry.registry import Registry

from fastsdk.service_interaction.api_seex import APISeex
from fastsdk.service_interaction.job_runtime import JobRuntime
from fastsdk.service_interaction.async_bridge import AsyncBridge
from fastsdk.service_interaction.provider_stack_registry import ProviderStackRegistry
from fastsdk.service_interaction.pipeline_planner import PipelinePlanner
from fastsdk.service_interaction.job_tasks import JobTasks
from meseex import MeseexBox


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
        self._job_tasks = JobTasks(stacks)
        self.meseex_box = MeseexBox(
            task_methods=self._job_tasks.as_task_map(),
            progress_verbosity=progress_verbosity,
        )
        self._bridge = AsyncBridge(self.meseex_box.task_executor.async_executor)

    def submit_job(self, service_id: str, endpoint_id: str, data: dict) -> APISeex:
        service = self.service_registry.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")

        endpoint = self.service_registry.get_endpoint(service_id, endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint {endpoint_id} not found in service {service_id}")

        stack = self.stacks.get(service_id)
        tasks = PipelinePlanner.plan(service, endpoint, stack)
        seex_name = f"{service.display_name}.{endpoint.path}"

        job = APISeex(
            service=service,
            endpoint=endpoint,
            data=data,
            tasks=tasks,
            name=seex_name,
        )
        job.runtime = JobRuntime(
            job=job,
            api_client=stack.api_client if stack else None,
            parser=stack.parser if stack else None,
            meseex_box=self.meseex_box,
            bridge=self._bridge,
        )
        return self.meseex_box.summon_meseex(job)
