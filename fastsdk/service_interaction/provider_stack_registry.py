"""Cache and resolve provider stacks per registered service and credential."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Optional, Tuple

from apipod_registry.registry import Registry
from socaity_schemas.platform import AIService

from fastsdk.service_interaction.provider_factory import ProviderFactory, ProviderStack
from fastsdk.service_interaction.request.file_handler import FileHandler

StackKey = Tuple[str, Optional[str]]


class ProviderStackRegistry:
    """Load and cache ``ProviderStack`` instances keyed by service id and API key.

    The API key is part of the key because the stack owns the credential used on
    every request. Caching by service id alone would hand the first caller's key
    to every later caller of the same service, which breaks multi-tenant hosts.
    """

    def __init__(self, registry: Registry, factory: Optional[ProviderFactory] = None):
        self.registry = registry
        self._factory = factory or ProviderFactory()
        self._stacks: Dict[StackKey, ProviderStack] = {}

    def get(self, service_id: str, api_key: str = None) -> Optional[ProviderStack]:
        """Return a cached stack, or ``None`` if this pair was never loaded."""
        return self._stacks.get((service_id, api_key))

    def require(self, service_id: str, api_key: str = None) -> ProviderStack:
        """Return a cached stack or raise."""
        stack = self._stacks.get((service_id, api_key))
        if stack is None:
            raise ValueError(
                f"No provider stack loaded for service {service_id}. "
                "Call ProviderStackRegistry.load(service_id, api_key) first."
            )
        return stack

    def ensure(self, service_id: str, api_key: str = None) -> ProviderStack:
        """Build and cache a stack when missing; return the cached stack."""
        key = (service_id, api_key)
        if key in self._stacks:
            return self._stacks[key]

        service = self.registry.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")

        self._stacks[key] = self._factory.build(service, api_key)
        return self._stacks[key]

    def load(self, service_name_or_id: str, api_key: str = None) -> AIService:
        """Resolve a service from the registry and ensure its provider stack is loaded."""
        service = self.registry.get_service(service_name_or_id)
        if not service:
            raise ValueError(f"Service {service_name_or_id} not found")

        self.ensure(service.id, api_key)
        return service

    def set_file_handler(self, service_id: str, file_handler: FileHandler, api_key: str = None) -> ProviderStack:
        """Replace the file handler on an existing stack."""
        stack = self.require(service_id, api_key)
        updated = replace(stack, file_handler=file_handler)
        self._stacks[(service_id, api_key)] = updated
        return updated

    def rebuild_file_handler(self, service_id: str, api_key: str = None) -> ProviderStack:
        """Rebuild the provider-default file handler on an existing stack."""
        stack = self.require(service_id, api_key)
        service = self.registry.get_service(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")

        provider_type = self._factory.determine_provider_type(service)
        handler = self._factory.build_file_handler(provider_type, api_key)
        updated = replace(stack, file_handler=handler)
        self._stacks[(service_id, api_key)] = updated
        return updated
