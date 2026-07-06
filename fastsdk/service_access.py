"""Accessors for the AIService aggregate as fastsdk uses it.

fastsdk works with one AIService that has exactly one primary deployment
(created via apipod_registry.create_service). These functions are the one
place that encodes this convention; callers never index deployments directly.
"""
from typing import Optional

from socaity_schemas.contract import ServiceAddress, ServiceContract
from socaity_schemas.platform import AIService, Deployment, Provider


def primary_deployment(service: AIService) -> Deployment:
    if not service.deployments:
        raise ValueError(f"Service {service.id} has no deployments")
    return service.deployments[0]


def service_contract(service: AIService) -> ServiceContract:
    contract = primary_deployment(service).contract
    if contract is None:
        raise ValueError(f"Service {service.id} has no materialized contract")
    return contract


def service_address(service: AIService) -> Optional[ServiceAddress]:
    return primary_deployment(service).address


def service_provider(service: AIService) -> Provider:
    return primary_deployment(service).provider


def needs_polling(service: AIService) -> bool:
    """Whether responses are job envelopes that must be polled.

    RunPod serverless always answers /run with a job envelope (the /run +
    /status wire protocol), even when the contract itself is synchronous.
    """
    return service_contract(service).has_job_queue or service_provider(service) == "runpod"
