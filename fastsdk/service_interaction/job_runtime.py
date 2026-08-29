"""Per-job lifecycle controller: cancel, stream, assemble, with guards.

``JobRuntime`` owns one job's transport lifecycle. The handle (``APISeex``) is a
ticket and delegates every lifecycle action here, so state that belongs to a
single job lives in this object, never on the process-level orchestrator:

- the one active ``StreamSession`` slot (``None`` or exactly one session)
- a readiness signal fed by the polling task as job state advances
- cancellation policy (remote cancel plus terminal-state reconciliation)
- stream teardown when a cancel resolves

Guards enforce the invariants: at most one active stream per job, no stream open
after a terminal state with no live source, and active streams close on cancel.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional, TYPE_CHECKING

from socaity_schemas import JOB_RESPONSE_TYPES

from fastsdk.service_interaction.response.sse_assembly import assemble_stream_bytes
from fastsdk.service_interaction.response.stream_session import StreamSession
from fastsdk.service_interaction.response.api_job_status import APIJobStatus

if TYPE_CHECKING:
    from meseex import MeseexBox
    from fastsdk.service_interaction.api_seex import APISeex
    from fastsdk.service_interaction.request import APIClient
    from fastsdk.service_interaction.response.response_parser import ResponseParser
    from fastsdk.service_interaction.async_bridge import AsyncBridge

logger = logging.getLogger(__name__)


class JobRuntime:
    """Lifecycle authority for a single ``APISeex`` job."""

    def __init__(
        self,
        job: "APISeex",
        api_client: Optional["APIClient"],
        parser: "ResponseParser",
        meseex_box: "MeseexBox",
        bridge: "AsyncBridge",
    ):
        self.job = job
        self._api_client = api_client
        self._parser = parser
        self._meseex_box = meseex_box
        self._bridge = bridge
        self._lock = threading.Lock()
        self._session: Optional[StreamSession] = None
        self._opening = False
        self._stream_ready = threading.Event()

    # ------------------------------------------------------------------
    # Readiness signal (fed by the orchestrator's send/poll tasks)
    # ------------------------------------------------------------------

    def refresh_stream_state(self) -> None:
        """Wake stream waiters once a live source appears or the job ends."""
        if self._has_stream_source() or self.job.is_terminal:
            self._stream_ready.set()

    def _has_stream_source(self) -> bool:
        if self.job.direct_response is not None:
            return True
        current = self.job.response
        return (
            self._api_client is not None
            and isinstance(current, JOB_RESPONSE_TYPES)
            and bool(self._api_client.get_stream_url(current))
        )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def stream(self, timeout_s: float = 60.0) -> StreamSession:
        """Open the job's live output stream and take the single session slot."""
        with self._lock:
            if self._session is not None or self._opening:
                raise RuntimeError(f"Job {self.job.meseex_id} already has an active stream")
            if self.job.is_terminal and not self._has_stream_source():
                raise ValueError(f"Job {self.job.meseex_id} exposes no stream")
            self._opening = True

        try:
            session = self._await_stream_source(timeout_s)
        finally:
            with self._lock:
                self._opening = False

        with self._lock:
            self._session = session
        return session

    def _await_stream_source(self, timeout_s: float) -> StreamSession:
        """Block on the readiness event until a source exists or the job ends."""
        deadline = time.monotonic() + timeout_s
        while True:
            session = self._resolve_source()
            if session is not None:
                return session
            if self.job.is_terminal:
                raise ValueError(f"Job {self.job.meseex_id} exposes no stream")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError(f"Job {self.job.meseex_id} exposes no stream")
            self._stream_ready.wait(timeout=remaining)
            self._stream_ready.clear()

    def _resolve_source(self) -> Optional[StreamSession]:
        """Return a session for a direct response or a discovered stream URL."""
        if self.job.direct_response is not None:
            return StreamSession(self.job.direct_response, self._bridge.loop)

        current = self.job.response
        if (
            self._api_client is not None
            and isinstance(current, JOB_RESPONSE_TYPES)
            and self._api_client.get_stream_url(current)
        ):
            response = self._bridge.run(self._api_client.open_stream, current)
            return StreamSession(response, self._bridge.loop)
        return None

    def assemble_result(self) -> Any:
        """Drain a streaming job into one assembled result (media file or text)."""
        session = self.stream()
        data = b"".join(session.iter_bytes())
        return assemble_stream_bytes(data, is_sse=session.is_sse)

    def _close_active_stream(self) -> None:
        """Release and close the session slot. Idempotent."""
        with self._lock:
            session = self._session
            self._session = None
        if session is not None:
            session.close()

    # ------------------------------------------------------------------
    # Cancellation (single source of truth for cancel semantics)
    # ------------------------------------------------------------------

    def cancel(self, wait: bool = False, timeout_s: float = 30.0, poll_interval_s: float = 0.5) -> Any:
        """Cancel the job remotely (provider permitting) and locally via the kernel."""
        self._close_active_stream()

        job = self.job
        if job.is_terminal:
            return job.cancel_result or job.response

        current_response = job.response
        has_cancel_url = (
            self._api_client is not None
            and isinstance(current_response, JOB_RESPONSE_TYPES)
            and self._api_client.get_cancel_url(current_response)
        )

        if not has_cancel_url:
            cancel_response = current_response or self._local_cancel_response(
                job, "Cancelled before remote job submission"
            )
            self._meseex_box.cancel_meseex(job, cancel_result=cancel_response)
            self._stream_ready.set()
            return cancel_response

        try:
            http_response = self._bridge.run(self._api_client.cancel_job, current_response, timeout_s=timeout_s)
            cancel_response = self._parse_cancel_response(http_response)
        except Exception as e:
            logger.warning("Remote cancellation for job %s failed: %s. Job will continue.", job.meseex_id, e)
            return current_response

        if cancel_response is None:
            job.set_cancel_result(current_response)
            return current_response

        status = self._api_client.get_status(cancel_response)
        if status == APIJobStatus.CANCELLED:
            self._meseex_box.cancel_meseex(job, cancel_result=cancel_response)
            self._stream_ready.set()
            return cancel_response

        if status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT, APIJobStatus.REJECTED}:
            job.set_cancel_result(cancel_response)
            return cancel_response

        job.set_cancel_result(cancel_response)
        if not wait:
            return cancel_response

        return self._wait_for_remote_cancellation(cancel_response, timeout_s, poll_interval_s)

    @staticmethod
    def _local_cancel_response(job: "APISeex", message: str) -> dict:
        return {"id": job.meseex_id, "status": "CANCELLED", "error": message}

    def _parse_cancel_response(self, http_response):
        error = self._bridge.run(self._parser.check_response_status, http_response)
        if error:
            if not http_response.is_closed:
                self._bridge.run(http_response.aclose)
            raise ValueError(f"Job cancellation failed: {error}")
        parsed = self._bridge.run(self._parser.parse_response, http_response, False)
        if not http_response.is_closed:
            self._bridge.run(http_response.aclose)
        return parsed if isinstance(parsed, JOB_RESPONSE_TYPES) else None

    def _wait_for_remote_cancellation(self, cancel_response, timeout_s, poll_interval_s):
        job = self.job
        current_response = cancel_response
        deadline = time.monotonic() + timeout_s

        while isinstance(current_response, JOB_RESPONSE_TYPES):
            status = self._api_client.get_status(current_response)
            if status == APIJobStatus.CANCELLED:
                self._meseex_box.cancel_meseex(job, cancel_result=current_response)
                self._stream_ready.set()
                return current_response

            if status in {APIJobStatus.FINISHED, APIJobStatus.FAILED, APIJobStatus.TIMEOUT, APIJobStatus.REJECTED}:
                job.set_cancel_result(current_response)
                return current_response

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                job.set_cancel_result(current_response)
                return current_response

            time.sleep(min(poll_interval_s, remaining))
            http_response = self._bridge.run(
                self._api_client.poll_status, current_response, timeout_s=min(remaining, 30.0)
            )
            next_response = self._parse_cancel_response(http_response)
            if next_response is None:
                job.set_cancel_result(current_response)
                return current_response
            current_response = next_response
        return current_response
