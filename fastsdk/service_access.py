"""Accessors for the Service aggregate as fastsdk uses it.

fastsdk works with one Service that has exactly one primary ServiceDetails
binding (created via apipod_registry.create_service). These functions are the
one place that encodes this convention; callers never index details directly.
"""
from typing import Optional

from socaity_schemas.public.spec.address import ServiceAddress
from socaity_schemas.public.spec.endpoint import ServiceContract
from socaity_schemas.platform.catalog.hosting import (
    Deployment,
    Provider,
)
from socaity_schemas.platform.catalog.service import (
    Service,
    ServiceDetails,
)


def primary_details(service: Service) -> ServiceDetails:
    if not service.details:
        raise ValueError(f"Service {service.id} has no details binding")
    return service.details[0]


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


def needs_polling(service: Service) -> bool:
    """Whether responses are job envelopes that must be polled.

    RunPod serverless always answers /run with a job envelope (the /run +
    /status wire protocol), even when the contract itself is synchronous.
    """
    return service_contract(service).has_job_queue or service_provider(service) == "runpod"
