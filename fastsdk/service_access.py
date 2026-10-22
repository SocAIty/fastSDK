"""Accessors for the Service aggregate as fastsdk uses it.

fastsdk invokes the active ServiceDetails binding of a Service
(``details[0]``). These functions are the one place that encodes
this convention; callers never index details directly.
"""
from typing import Optional

from apipod_registry import active_details
from socaity_schemas.public.spec.address import ServiceAddress
from socaity_schemas.public.spec.endpoint import ServiceContract
from socaity_schemas.platform.catalog.hosting import (
    Deployment,
    Provider,
    RunpodRuntime,
)
from socaity_schemas.platform.catalog.service import (
    Service,
    ServiceDetails,
)

# Vault slot of Runpod Public Endpoint keys. RUNPOD_API_KEY provisions Socaity-hosted
# Runpod services and must never reach a Public Endpoint.
RUNPOD_PUBLIC_CREDENTIAL = "runpod-public"


def primary_details(service: Service) -> ServiceDetails:
    details = active_details(service)
    if details is None:
        raise ValueError(f"Service {service.id} has no active details binding")
    return details


def details_provider(details: ServiceDetails) -> Provider:
    """Compute provider from the nested deployment. Connectors have none."""
    dep = details.deployment
    if dep is not None and dep.provider:
        return dep.provider
    return "other"


def details_address(details: ServiceDetails) -> Optional[ServiceAddress]:
    """Reachability URL: deployment or connector, never details."""
    if details.deployment is not None and details.deployment.address is not None:
        return details.deployment.address
    if details.connector is not None and details.connector.address is not None:
        return details.connector.address
    return None


def set_reachability(
    details: ServiceDetails,
    *,
    provider: Optional[Provider] = None,
    address: Optional[ServiceAddress] = None,
) -> None:
    """Write provider/url onto the nested instance, never onto details."""
    if details.connector is not None:
        if address is not None:
            details.connector.address = address
        return
    if details.deployment is None:
        details.deployment = Deployment(
            service_id=details.service_id,
            details_id=details.id,
            provider=provider or "other",
        )
    if provider is not None:
        details.deployment.provider = provider
    if address is not None:
        details.deployment.address = address


def service_contract(service: Service) -> ServiceContract:
    contract = primary_details(service).contract
    if contract is None:
        raise ValueError(f"Service {service.id} has no materialized contract")
    return contract


def service_address(service: Service) -> Optional[ServiceAddress]:
    return details_address(primary_details(service))


def service_provider(service: Service) -> Provider:
    return details_provider(primary_details(service))


def is_runpod_public_endpoint(service: Service) -> bool:
    """A Runpod deployment whose provider_config names the Public Endpoint runtime."""
    deployment = primary_details(service).deployment
    if deployment is None or deployment.provider != "runpod" or deployment.provider_config is None:
        return False
    return isinstance(deployment.provider_config.runtime, RunpodRuntime)


def service_credential_name(service: Service) -> str:
    """Credential slot whose secret is the provider bearer for this service."""
    if is_runpod_public_endpoint(service):
        return RUNPOD_PUBLIC_CREDENTIAL
    return service_provider(service)


def needs_polling(service: Service) -> bool:
    """Whether responses are job envelopes that must be polled.

    RunPod serverless always answers /run with a job envelope (the /run +
    /status wire protocol), even when the contract itself is synchronous.
    The Socaity gate enqueues every call, MCP tools included.
    """
    return service_contract(service).has_job_queue or service_provider(service) in ("runpod", "socaity")
