from __future__ import annotations
from typing import Dict, TYPE_CHECKING
if TYPE_CHECKING:
    from fastsdk import ServiceClient

from singleton_decorator import singleton


@singleton
class Registry:
    """
    The registry holds all references to services which were instantiated.
    It provides functions, to list and search services and endpoints.
    """
    def __init__(self):
        self._services = {}

    def add_service(self, name: str, obj: ServiceClient):
        self._services[name] = obj

    def remove_service(self, name: str):
        self._services.pop(name)

    def get_services(self) -> Dict[str, ServiceClient]:
        return self._services

    def list_endpoints(self):
        """
        List all available endpoints of the service with their parameters.
        :return: a list of endpoint names
        """
        for name, srvc in self._services.items():
            print(f"{name}: {srvc.list_endpoints()}")