"""Build provider-specific client, file handler, and parser stacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from apipod_registry.schemas.service_definitions import (
    ServiceDefinition,
    ServiceAddress,
    RunpodServiceAddress,
    ReplicateServiceAddress,
    SocaityServiceAddress,
)
from fastCloud import ReplicateUploadAPI

from fastsdk.service_interaction.request import (
    APIClient,
    APIClientReplicate,
    APIClientRunpod,
    APIClientSocaity,
)
from fastsdk.service_interaction.request.api_client_runpod import APIClientRunpodApipod
from fastsdk.service_interaction.request.file_handler import FileHandler
from fastsdk.service_interaction.response.response_parser import ResponseParser


@dataclass(frozen=True)
class ProviderStack:
    """Resolved provider wiring for one service."""

    provider_type: str
    api_client: APIClient
    file_handler: FileHandler
    parser: ResponseParser


class ProviderFactory:
    """Resolve provider type and assemble the client/handler/parser stack."""

    _CLIENT_CLASSES = {
        "runpod": APIClientRunpod,
        "runpod_apipod": APIClientRunpodApipod,
        "socaity": APIClientSocaity,
        "replicate": APIClientReplicate,
    }

    def __init__(self):
        self._parser_cache: Dict[str, ResponseParser] = {}

    @staticmethod
    def determine_provider_type(service_def: ServiceDefinition) -> str:
        """Map a service definition to a provider key."""
        addr = service_def.service_address
        if isinstance(addr, RunpodServiceAddress):
            if service_def.specification in ("apipod", "socaity"):
                return "runpod_apipod"
            return "runpod"
        if isinstance(addr, SocaityServiceAddress):
            return "socaity"
        if isinstance(addr, ReplicateServiceAddress):
            return "replicate"
        if isinstance(addr, ServiceAddress):
            if service_def.specification in ("apipod", "socaity"):
                return "socaity"
            if service_def.specification == "runpod":
                return "runpod"
        return "other"

    def get_parser(self, provider_type: str) -> ResponseParser:
        """Return a cached parser for the provider type."""
        if provider_type not in self._parser_cache:
            self._parser_cache[provider_type] = ResponseParser(provider_type)
        return self._parser_cache[provider_type]

    def build_file_handler(self, provider_type: str, api_key: str = None) -> FileHandler:
        """Create the file handler configured for the provider."""
        if provider_type == "socaity":
            return FileHandler(file_format="httpx", upload_to_cloud_threshold_mb=0, max_upload_file_size_mb=300)
        if provider_type in ("runpod", "runpod_apipod"):
            return FileHandler(file_format="base64", max_upload_file_size_mb=300)
        if provider_type == "replicate":
            fast_cloud = ReplicateUploadAPI(api_key=api_key)
            return FileHandler(
                fast_cloud=fast_cloud,
                file_format="base64",
                upload_to_cloud_threshold_mb=0,
                max_upload_file_size_mb=300,
            )
        return FileHandler()

    def build(self, service_def: ServiceDefinition, api_key: str = None) -> ProviderStack:
        """Assemble the full provider stack for a service."""
        if not hasattr(service_def, "service_address") or service_def.service_address is None:
            raise ValueError(
                f"Service {service_def.id} has no service address. "
                "Add one with Registry.update_service(service_id, service_address=...)"
            )

        provider_type = self.determine_provider_type(service_def)
        client_cls = self._CLIENT_CLASSES.get(provider_type, APIClient)
        api_client = client_cls(service_def=service_def, api_key=api_key)
        file_handler = self.build_file_handler(provider_type, api_key)
        parser = self.get_parser(provider_type)

        return ProviderStack(
            provider_type=provider_type,
            api_client=api_client,
            file_handler=file_handler,
            parser=parser,
        )
