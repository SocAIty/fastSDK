"""Cache and resolve provider stacks per registered service."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Optional

from apipod_registry.registry import Registry
from apipod_registry.schemas.service_definitions import ServiceDefinition

from fastsdk.service_interaction.provider_factory import ProviderFactory, ProviderStack
from fastsdk.service_interaction.request.file_handler import FileHandler


class ProviderStackRegistry:
    """Load and cache ``ProviderStack`` instances keyed by service id."""

    def __init__(self, registry: Registry, factory: Optional[ProviderFactory] = None):
        self.registry = registry
        self._factory = factory or ProviderFactory()
        self._stacks: Dict[str, ProviderStack] = {}

    def get(self, service_id: str) -> Optional[ProviderStack]:
        """Return a cached stack, or ``None`` if the service was never loaded."""
        return self._stacks.get(service_id)

    def require(self, service_id: str) -> ProviderStack:
        """Return a cached stack or raise."""
        stack = self._stacks.get(service_id)
        if stack is None:
            raise ValueError(
                f"No provider stack loaded for service {service_id}. "
                "Call ProviderStackRegistry.load(service_id, api_key) first."
            )
        return stack

    def ensure(self, service_id: str, api_key: str = None) -> ProviderStack:
        """Build and cache a stack when missing; return the cached stack."""
        if service_id in self._stacks:
            return self._stacks[service_id]

        service_def = self.registry.get_service(service_id)
        if not service_def:
            raise ValueError(f"Service {service_id} not found")

        self._stacks[service_id] = self._factory.build(service_def, api_key)
        return self._stacks[service_id]

    def load(self, service_name_or_id: str, api_key: str = None) -> ServiceDefinition:
        """Resolve a service from the registry and ensure its provider stack is loaded."""
        service_def = self.registry.get_service(service_name_or_id)
        if not service_def:
            raise ValueError(f"Service {service_name_or_id} not found")

        self.ensure(service_def.id, api_key)
        return service_def

    def set_file_handler(self, service_id: str, file_handler: FileHandler) -> ProviderStack:
        """Replace the file handler on an existing stack."""
        stack = self.require(service_id)
        updated = replace(stack, file_handler=file_handler)
        self._stacks[service_id] = updated
        return updated

    def rebuild_file_handler(self, service_id: str, api_key: str = None) -> ProviderStack:
        """Rebuild the provider-default file handler on an existing stack."""
        stack = self.require(service_id)
        service_def = self.registry.get_service(service_id)
        if not service_def:
            raise ValueError(f"Service {service_id} not found")

        provider_type = self._factory.determine_provider_type(service_def)
        handler = self._factory.build_file_handler(provider_type, api_key)
        updated = replace(stack, file_handler=handler)
        self._stacks[service_id] = updated
        return updated
