from socaity_schemas.contract import Endpoint
from socaity_schemas.platform import AIService
from socaity_schemas import JOB_RESPONSE_TYPES, StreamingResponse
from meseex import MrMeseex

from fastsdk.service_access import service_provider

from typing import Any, Optional, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    import httpx
    from fastsdk.service_interaction.job_runtime import JobRuntime
    from fastsdk.service_interaction.provider_factory import ProviderStack
    from fastsdk.service_interaction.response.stream_session import StreamSession


class APISeex(MrMeseex):
    """User-facing handle for an API job: identity plus a progress/result view.

    A ticket, not an orchestrator. Lifecycle actions (cancel, stream) delegate to
    a per-job ``JobRuntime`` set by ``ApiJobManager`` at submit time. The handle
    never talks to HTTP clients, parsers, or the ``MeseexBox`` directly.
    """

    def __init__(
        self,
        service: AIService,
        endpoint: Endpoint,
        data: Any = None,
        name: str = None,
        tasks: list = None,
        stack: Optional["ProviderStack"] = None,
        materialize_media: bool = True,
    ):
        super().__init__(tasks, data, name)
        self.service = service
        self.endpoint = endpoint
        # Credential-bound provider wiring, resolved once at submit time so no
        # pipeline task re-resolves it (and cannot pick up another tenant's key).
        self.stack = stack
        # When False, media results stay URL references instead of being downloaded.
        self.materialize_media = materialize_media
        # Per-job lifecycle controller, assigned by the orchestrator after creation.
        self.runtime: Optional["JobRuntime"] = None
        # Set by the orchestrator when the initial response is a live stream.
        self.direct_response: Optional["httpx.Response"] = None

    @property
    def provider_stack(self) -> "ProviderStack":
        """The stack bound at submit time; raises when the job was never wired."""
        if self.stack is None:
            raise ValueError(
                f"No provider stack bound to job for service {self.service.id}. "
                "Submit through ApiJobManager.submit_job()."
            )
        return self.stack

    # ------------------------------------------------------------------
    # Domain view
    # ------------------------------------------------------------------

    @property
    def response(self):
        """Returns the latest parsed job response from the API, or None."""
        if self.termination_state is not None and isinstance(self.cancel_result, JOB_RESPONSE_TYPES):
            return self.cancel_result

        resp = self.get_task_output("Polling")
        if resp is not None:
            return resp
        return self.get_task_output("Sending request")

    @property
    def runtime_info(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns (delay_seconds, execution_seconds) normalised to seconds."""
        delay_seconds: Optional[float] = None
        execution_seconds: Optional[float] = None

        resp = self.response
        if not resp:
            return None, None

        provider = service_provider(self.service)

        if provider == "runpod":
            delay_ms = getattr(resp, "delayTime", None)
            execution_ms = getattr(resp, "executionTime", None)
            if delay_ms is not None:
                delay_seconds = float(delay_ms) / 1000.0
            if execution_ms is not None:
                execution_seconds = float(execution_ms) / 1000.0

        elif provider == "replicate":
            created_str = getattr(resp, "created_at", None)
            started_str = getattr(resp, "started_at", None)
            if created_str and started_str:
                try:
                    t1 = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(str(started_str).replace("Z", "+00:00"))
                    delay_seconds = (t2 - t1).total_seconds()
                except (ValueError, TypeError):
                    pass
            exec_ms = getattr(resp, "execution_time_ms", None)
            if exec_ms is not None:
                execution_seconds = float(exec_ms) / 1000.0

        elif provider == "socaity":
            metrics = getattr(resp, "metrics", None)
            if metrics:
                delay_seconds = getattr(metrics, "platform_queue_time_s", None)
                execution_seconds = getattr(metrics, "execution_time_s", None)

        return delay_seconds, execution_seconds

    # ------------------------------------------------------------------
    # Lifecycle delegation (syntactic sugar over the runtime port)
    # ------------------------------------------------------------------

    def cancel(self, *args, **kwargs) -> Any:
        if self.runtime is None:
            return super().cancel(*args, **kwargs)
        return self.runtime.cancel(*args, **kwargs)

    def stream(self, **kwargs) -> "StreamSession":
        """Open the job's live output stream. The session iterates sync or async."""
        return self.runtime.stream(**kwargs)

    def get_result(self, *args, **kwargs) -> Any:
        result = super().get_result(*args, **kwargs)
        if isinstance(result, StreamingResponse) and self.runtime is not None:
            return self.runtime.assemble_result()
        return result
