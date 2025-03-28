from __future__ import annotations
from typing import Dict, TYPE_CHECKING, Union, Optional

if TYPE_CHECKING:
    from fastsdk import APIClient

from singleton_decorator import singleton


@singleton
class Registry:
    """
    The registry holds all references to services which were instantiated.
    It provides functions, to list and search services and endpoints.
    """
    def __init__(self):
        self._services = {}

    def add_service(self, name: str, obj: APIClient):
        if name is None or not isinstance(name, str):
            raise ValueError("service_name must be given and be a string.")

        self._services[name] = obj

    def remove_service(self, service: Union[APIClient, str]):
        if isinstance(service, str):
            self._services.pop(service)
        elif isinstance(service, APIClient):
            self._services.pop(service.service_name)

    def get_services(self, name_filter: Optional[str] = None) -> Dict[str, APIClient]:
        if not name_filter:
            return self._services

        return {name: srvc for name, srvc in self._services.items() if name_filter in name}

    def list_endpoints(self):
        """
        List all available endpoints of the service with their parameters.
        :return: a list of endpoint names
        """
        for name, srvc in self._services.items():
            print(f"{name}: {srvc.list_endpoints()}")