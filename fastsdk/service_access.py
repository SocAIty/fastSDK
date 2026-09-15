"""Accessors for the Service aggregate as fastsdk uses it.

fastsdk works with one Service that has exactly one primary ServiceDetails
binding (created via apipod_registry.create_service). These functions are the
one place that encodes this convention; callers never index details directly.
"""
from typing import Optional

from socaity_schemas.contract import ServiceAddress, ServiceContract
from socaity_schemas.platform import Provider, Service, ServiceDetails


def primary_details(service: Service) -> ServiceDetails:
    if not service.details:
        raise ValueError(f"Service {service.id} has no details binding")
    return service.details[0]


def service_contract(service: Service) -> ServiceContract:
    contract = primary_details(service).contract
    if contract is None:
        raise ValueError(f"Service {service.id} has no materialized contract")
    return contract


def service_address(service: Service) -> Optional[ServiceAddress]:
    return primary_details(service).address


def service_provider(service: Service) -> Provider:
    return primary_details(service).provider


def needs_polling(service: Service) -> bool:
    """Whether responses are job envelopes that must be polled.

    RunPod serverless always answers /run with a job envelope (the /run +
    /status wire protocol), even when the contract itself is synchronous.
    """
    return service_contract(service).has_job_queue or service_provider(service) == "runpod"
