"""Build provider-specific client, file handler, and parser stacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from socaity_schemas.platform import AIService
from fastCloud import ReplicateUploadAPI

from fastsdk.service_access import service_address, service_contract, service_provider
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
        "apipod-serverless-runpod": APIClientRunpodApipod,
        "socaity": APIClientSocaity,
        # The APIPod wire protocol (job envelopes + links) is the Socaity protocol,
        # so self-hosted apipod services (e.g. localhost) use the same client.
        "apipod": APIClientSocaity,
        "replicate": APIClientReplicate,
    }

    def __init__(self):
        self._parser_cache: Dict[str, ResponseParser] = {}

    @staticmethod
    def determine_provider_type(service: AIService) -> str:
        """Map a service to the provider type key used by clients and response parsers."""
        provider = service_provider(service)
        specification = service_contract(service).specification

        if provider == "runpod":
            return "apipod-serverless-runpod" if specification == "apipod" else "runpod"
        if provider == "socaity":
            return "socaity"
        if provider == "replicate":
            return "replicate"
        if specification == "apipod":
            return "apipod"
        return "other"

    def get_parser(self, provider_type: str) -> ResponseParser:
        """Return a cached parser for the provider type."""
        if provider_type not in self._parser_cache:
            self._parser_cache[provider_type] = ResponseParser(provider_type)
        return self._parser_cache[provider_type]

    def build_file_handler(self, provider_type: str, api_key: str = None) -> FileHandler:
        """Create the file handler configured for the provider."""
        if provider_type in ("socaity", "apipod"):
            return FileHandler(file_format="httpx", upload_to_cloud_threshold_mb=0, max_upload_file_size_mb=300)
        if provider_type in ("runpod", "apipod-serverless-runpod"):
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

    def build(self, service: AIService, api_key: str = None) -> ProviderStack:
        """Assemble the full provider stack for a service."""
        if service_address(service) is None:
            raise ValueError(
                f"Service {service.id} has no deployment address. "
                "Add one with fastsdk.register_service(..., service_address=...)"
            )

        provider_type = self.determine_provider_type(service)
        client_cls = self._CLIENT_CLASSES.get(provider_type, APIClient)
        api_client = client_cls(service=service, api_key=api_key)
        file_handler = self.build_file_handler(provider_type, api_key)
        parser = self.get_parser(provider_type)

        return ProviderStack(
            provider_type=provider_type,
            api_client=api_client,
            file_handler=file_handler,
            parser=parser,
        )
