from socaity_schemas.contract import Endpoint
from socaity_schemas.platform import AIService
from socaity_schemas import JOB_RESPONSE_TYPES, StreamingResponse
from meseex import MrMeseex

from fastsdk.service_access import service_provider

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    import httpx
    from fastsdk.service_interaction.job_runtime import JobRuntime
    from fastsdk.service_interaction.provider_factory import ProviderStack
    from fastsdk.service_interaction.response.stream_session import StreamSession


Unsubscribe = Callable[[], None]
JobCallback = Callable[["JobEvent"], None]


@dataclass
class JobEvent:
    """Lifecycle event of an ``APISeex`` job.

    ``kind`` is one of ``started``, ``progress``, ``finished``, ``error``.
    """

    kind: str
    job_id: Optional[str] = None
    progress: Optional[float] = None
    message: Optional[str] = None
    result: Any = None
    error: Optional[BaseException] = None


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
        self._sub_lock = Lock()
        self._subscribers: List[dict] = []
        self._started_event: Optional[JobEvent] = None
        self._progress_event: Optional[JobEvent] = None
        self._terminal_event: Optional[JobEvent] = None
        self._progress_key: Optional[tuple] = None

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
        sent = self.get_task_output("Sending request")
        if sent is not None:
            return sent
        attached = self.get_task_output("Attach")
        if attached is not None:
            return attached
        if isinstance(self.input, JOB_RESPONSE_TYPES):
            return self.input
        return None

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

    @property
    def platform_job_id(self) -> Optional[str]:
        """Platform job id once the gateway assigned one."""
        resp = self.response
        if resp is None:
            return None
        return getattr(resp, "job_id", None) or getattr(resp, "id", None)

    def subscribe(
        self,
        on_started: Optional[JobCallback] = None,
        on_progress: Optional[JobCallback] = None,
        on_finished: Optional[JobCallback] = None,
        on_error: Optional[JobCallback] = None,
        replay: bool = True,
    ) -> Unsubscribe:
        """Subscribe to job lifecycle events. Thread-safe; callbacks never fail the job.

        ``started`` means the platform job id is available. Progress fires when the
        progress message or status changes, not on percentage-only ticks. Success or
        error is emitted exactly once. ``replay=True`` delivers the current start,
        progress, and terminal events to a late subscriber.
        """
        entry = {
            "on_started": on_started,
            "on_progress": on_progress,
            "on_finished": on_finished,
            "on_error": on_error,
        }
        with self._sub_lock:
            self._subscribers.append(entry)
            snapshot = (
                self._started_event,
                self._progress_event,
                self._terminal_event,
            ) if replay else (None, None, None)
        if replay:
            started, progress, terminal = snapshot
            if started is not None:
                self._safe_call(on_started, started)
            if progress is not None:
                self._safe_call(on_progress, progress)
            if terminal is not None:
                if terminal.kind == "error":
                    self._safe_call(on_error, terminal)
                else:
                    self._safe_call(on_finished, terminal)

        def unsubscribe() -> None:
            with self._sub_lock:
                try:
                    self._subscribers.remove(entry)
                except ValueError:
                    pass

        return unsubscribe

    def notify_started(self, job_id: Optional[str] = None) -> None:
        """Emit ``started`` once the platform job id is known."""
        job_id = job_id or self.platform_job_id
        if not job_id:
            return
        event = JobEvent(kind="started", job_id=job_id)
        with self._sub_lock:
            if self._started_event is not None:
                return
            self._started_event = event
            listeners = [entry.get("on_started") for entry in self._subscribers]
        for callback in listeners:
            self._safe_call(callback, event)

    def notify_progress(
        self,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        """Emit ``progress`` when the message or status changes."""
        key = (message, status)
        with self._sub_lock:
            if key == self._progress_key:
                return
            self._progress_key = key
            event = JobEvent(
                kind="progress",
                job_id=self.platform_job_id,
                progress=progress,
                message=message or status,
            )
            self._progress_event = event
            listeners = [entry.get("on_progress") for entry in self._subscribers]
        for callback in listeners:
            self._safe_call(callback, event)

    def notify_finished(self, result: Any = None) -> None:
        """Emit terminal success exactly once."""
        event = JobEvent(
            kind="finished",
            job_id=self.platform_job_id,
            result=result if result is not None else self.result,
        )
        listeners = self._store_terminal(event)
        for callback in listeners:
            self._safe_call(callback, event)

    def notify_error(self, error: BaseException) -> None:
        """Emit terminal failure exactly once."""
        event = JobEvent(
            kind="error",
            job_id=self.platform_job_id,
            error=error,
        )
        with self._sub_lock:
            if self._terminal_event is not None:
                return
            self._terminal_event = event
            listeners = [entry.get("on_error") for entry in self._subscribers]
        for callback in listeners:
            self._safe_call(callback, event)

    def _store_terminal(self, event: JobEvent) -> list:
        with self._sub_lock:
            if self._terminal_event is not None:
                return []
            self._terminal_event = event
            key = "on_error" if event.kind == "error" else "on_finished"
            return [entry.get(key) for entry in self._subscribers]

    @staticmethod
    def _safe_call(callback: Optional[JobCallback], event: JobEvent) -> None:
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            pass

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
