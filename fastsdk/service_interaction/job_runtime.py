"""Narrow lifecycle port between a job handle and its orchestrator.

``APISeex`` is a ticket: identity plus a progress/result view. All I/O and state
transitions stay with the orchestrator (``ApiJobManager``). The handle reaches the
orchestrator only through this port, never through HTTP clients, parsers, or the
``MeseexBox``. That keeps lifecycle authority in one place and stops the handle
from growing transport code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fastsdk.service_interaction.api_seex import APISeex
    from fastsdk.service_interaction.response.stream_session import StreamSession


class JobRuntimePort(ABC):
    """Lifecycle operations a handle delegates to its orchestrator."""

    @abstractmethod
    def cancel(
        self,
        job: "APISeex",
        wait: bool = False,
        timeout_s: float = 30.0,
        poll_interval_s: float = 0.5,
    ) -> Any:
        """Cancel the job remotely and locally. Single source of truth."""

    @abstractmethod
    def stream(self, job: "APISeex", **kwargs) -> "StreamSession":
        """Open a live output stream for the job, consumable from any thread."""

    @abstractmethod
    def astream(self, job: "APISeex", **kwargs) -> "StreamSession":
        """Open a live output stream for the job, consumable from any loop."""

    @abstractmethod
    def assemble_result(self, job: "APISeex") -> Any:
        """Drain a streaming job into one assembled result (media file or text)."""
