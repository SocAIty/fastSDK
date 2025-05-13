from abc import ABC, abstractmethod
from typing import List, Dict
from fastsdk.service_management.service_definition import ServiceDefinition


class IServiceStore(ABC):
    """
    Abstract base class for service stores.
    """
    @abstractmethod
    def load_service(self, id_or_name: str) -> ServiceDefinition:
        """
        Loads a service from storage or source.
        """
        pass

    @abstractmethod
    def save_service(self, service: ServiceDefinition):
        """
        Saves a service to storage or source.
        """
        pass

    @abstractmethod
    def delete_service(self, id_or_name: str):
        """
        Deletes a service from storage or source.
        """
        pass

    @abstractmethod
    def list_services(self) -> List[ServiceDefinition]:
        """
        Lists all services in storage or source.
        """
        pass

    @abstractmethod
    def get_version_index(self) -> Dict[str, str]:
        """
        Get the version index from storage or source. Returns a dict in form {service_id: version}.
        """
        pass