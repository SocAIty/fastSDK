"""Plan the meseex task pipeline for a job submission."""

from __future__ import annotations

from typing import List, Optional

from socaity_schemas.public.spec.endpoint import Endpoint
from socaity_schemas.platform.catalog.service import Service

from fastsdk.service_access import needs_polling
from fastsdk.service_interaction.provider_factory import ProviderStack

_FILE_FORMATS = frozenset({"file", "image", "video", "audio"})


class PipelinePlanner:
    """Derive the ordered task list for one endpoint invocation."""

    @staticmethod
    def _endpoint_has_file_params(endpoint: Endpoint) -> bool:
        for param in endpoint.parameters:
            definitions = getattr(param, "definition", None)
            if definitions is None:
                continue
            defs = definitions if isinstance(definitions, list) else [definitions]
            if any(getattr(d, "format", None) in _FILE_FORMATS for d in defs):
                return True
        return False

    @staticmethod
    def _needs_upload(stack: Optional[ProviderStack]) -> bool:
        if stack is None:
            return False
        fh = stack.file_handler
        return hasattr(fh, "fast_cloud") and fh.fast_cloud is not None

    @classmethod
    def plan(
        cls,
        service: Service,
        endpoint: Endpoint,
        stack: Optional[ProviderStack] = None,
    ) -> List[str]:
        """Return the ordered meseex task names for this submission."""
        tasks = ["Preparing"]

        if cls._endpoint_has_file_params(endpoint):
            tasks.append("Load files")

        if cls._needs_upload(stack):
            tasks.append("Uploading files")

        tasks.append("Sending request")

        if needs_polling(service):
            tasks.append("Polling")
            if cls._needs_status_stream(stack):
                tasks.append("Streaming")

        tasks.append("Processing result")
        return tasks

    @staticmethod
    def _needs_status_stream(stack: Optional[ProviderStack]) -> bool:
        return stack is not None and stack.provider_type == "socaity"

    @classmethod
    def plan_track(cls, stack: Optional[ProviderStack] = None) -> List[str]:
        """Task list for ``track_job``: attach an envelope, then the wait phases."""
        tasks = ["Attach", "Polling"]
        if cls._needs_status_stream(stack):
            tasks.append("Streaming")
        tasks.append("Processing result")
        return tasks
