"""Plan the meseex task pipeline for a job submission."""

from __future__ import annotations

from typing import List, Optional

from apipod_registry.schemas.service_definitions import EndpointDefinition, ServiceDefinition

from fastsdk.service_interaction.provider_factory import ProviderStack

_FILE_FORMATS = frozenset({"file", "image", "video", "audio"})
_POLLING_SPECIFICATIONS = frozenset({"apipod", "socaity", "runpod", "replicate"})


class PipelinePlanner:
    """Derive the ordered task list for one endpoint invocation."""

    @staticmethod
    def _endpoint_has_file_params(endpoint_def: EndpointDefinition) -> bool:
        for param in endpoint_def.parameters:
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
        service_def: ServiceDefinition,
        endpoint_def: EndpointDefinition,
        stack: Optional[ProviderStack] = None,
    ) -> List[str]:
        """Return the ordered meseex task names for this submission."""
        tasks = ["Preparing"]

        if cls._endpoint_has_file_params(endpoint_def):
            tasks.append("Load files")

        if cls._needs_upload(stack):
            tasks.append("Uploading files")

        tasks.append("Sending request")

        if service_def.specification in _POLLING_SPECIFICATIONS:
            tasks.append("Polling")

        tasks.append("Processing result")
        return tasks
