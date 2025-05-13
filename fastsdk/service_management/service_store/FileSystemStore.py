import os
from typing import Union, Dict, List
from fastsdk.service_management.service_definition import ServiceDefinition
from fastsdk.service_management.service_store.IServiceStore import IServiceStore
import json


class FileSystemStore(IServiceStore):
    def __init__(self, path: str = None):
        """
        Will manage cached service definitions in the file system. Also uses a index file to store service ids and their hashed version.
        :param base_path: The base path to store the service definitions. If not None will be package_path/cache
        """
        self.base_path = path or os.path.join(os.path.dirname(__file__), "..", "..", "cache")
        self._index = None
        self.get_version_index()
  
    def load_service(self, id_or_name: str) -> Union[ServiceDefinition, None]:
        """
        Loads a service from the file system.
        :param id_or_name: The ID or name of the service.
        :return: The service definition or None if not found.
        """
        fp = os.path.join(self.base_path, f"{id_or_name}.json")
        if not os.path.exists(fp):
            return None
        with open(fp, "r") as f:
            data = json.load(f)
            return ServiceDefinition(**data)

    def save_service(self, service: ServiceDefinition):
        """
        Saves a service to the file system.
        :param service: The service definition to save.
        """
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

        fp = os.path.join(self.base_path, f"{service.id}.json")
        with open(fp, "w") as f:
            json.dump(service.model_dump(), f)

        self._index[service.id] = service.version
        self.save_index()

    def save_index(self):
        with open(os.path.join(self.base_path, "version_index.json"), "w") as f:
            json.dump(self._index, f)
        
    def get_version_index(self) -> Dict[str, str]:
        if not self._index:
            index_fp = os.path.join(self.base_path, "version_index.json")
            if os.path.exists(index_fp):
                with open(index_fp, "r") as f:
                    self._index = json.load(f)
            else:
                self._index = {}
        return self._index

    def delete_service(self, id_or_name: str):
        fp = os.path.join(self.base_path, f"{id_or_name}.json")
        if os.path.exists(fp):
            os.remove(fp)
            del self._index[id_or_name]
            self.save_index()

    def list_services(self) -> List[ServiceDefinition]:
        return [self.load_service(id_or_name) for id_or_name in self._index.keys()]

