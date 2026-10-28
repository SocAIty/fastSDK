from typing import Dict, Optional

from apipod_registry.registry import Registry
from socaity_schemas.public.providers import (
    JobLinks,
    SocaityJobResponse,
)

from fastsdk.service_access import RUNPOD_PUBLIC_CREDENTIAL, service_contract, service_credential_name
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
        self._job_tasks = JobTasks()
        self.meseex_box = MeseexBox(
            task_methods=self._job_tasks.as_task_map(),
            progress_verbosity=progress_verbosity,
        )
        self._bridge = AsyncBridge(self.meseex_box.task_executor.async_executor)

    def submit_job(
        self,
        service_id: str,
        operation: Optional[str],
        data: dict,
        api_key: str = None,
        materialize_media: bool = True,
        credentials: Optional[Dict[str, str]] = None,
    ) -> APISeex:
        """Submit one operation call.

        Args:
            credentials: Secrets for this job by security scheme name. An entry named after a
                preset provider (``replicate``, ``runpod``, ``socaity``) replaces ``api_key`` as
                that provider's bearer, so one host can run jobs on behalf of several accounts.
                Runpod Public Endpoints read ``runpod-public`` instead of ``runpod``.
        """
        service = self.service_registry.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")

        endpoint = self.service_registry.get_operation(service_id, operation)
        if not endpoint:
            raise ValueError(f"Operation '{operation}' not found in service {service_id}")

        credentials = credentials or {}
        credential_name = service_credential_name(service)
        # A Public Endpoint key on a service that resolves to Socaity-hosted Runpod means the
        # runtime was lost on the way. Falling back to api_key would bill the infra account.
        if credential_name == "runpod" and RUNPOD_PUBLIC_CREDENTIAL in credentials and "runpod" not in credentials:
            raise ValueError(
                f"Service {service_id} has a {RUNPOD_PUBLIC_CREDENTIAL} credential but no Runpod Public Endpoint runtime"
            )
        stack = self.stacks.ensure(service_id, credentials.get(credential_name) or api_key)
        tasks = PipelinePlanner.plan(service, endpoint, stack)
        seex_name = f"{service.display_name}.{endpoint.operation_key}"

        job = APISeex(
            service=service,
            endpoint=endpoint,
            data=data,
            tasks=tasks,
            name=seex_name,
            stack=stack,
            materialize_media=materialize_media,
            credentials=credentials,
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

    def track_job(
        self,
        service_id: str,
        job_id: str,
        api_key: str = None,
        materialize_media: bool = True,
    ) -> APISeex:
        """Re-attach to a running job on a registered service and poll until terminal."""
        service = self.service_registry.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")

        endpoints = service_contract(service).endpoints
        if not endpoints:
            raise ValueError(f"Service {service_id} has no endpoints to attach a job")
        endpoint = endpoints[0]

        stack = self.stacks.ensure(service_id, api_key)
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
            tasks=PipelinePlanner.plan_track(stack),
            name=f"track:{job_id}",
            stack=stack,
            materialize_media=materialize_media,
        )
        return self._wire(job, stack)
