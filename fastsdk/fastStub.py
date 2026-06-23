from apipod_registry.definitions.service_definitions import ServiceDefinition


import importlib.util
from typing import Iterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fastsdk.fastClient import FastClient


class FastStub:
    """
    Result of generate_stub(). Holds everything you need to use the generated client stub:
    - path: where the .py file was written (import it from there in your next run)
    - class_name: the name of the generated class inside that file
    - service_definition: the parsed service the stub was generated from
    - client(): import the generated file and return a ready-to-use client instance
    """
    def __init__(self, path: str, class_name: str, service_definition: ServiceDefinition):
        self.path: str = path
        self.class_name: str = class_name
        self.service_definition: ServiceDefinition = service_definition

    def client(self, api_key: Optional[str] = None) -> 'FastClient':
        """Import the generated stub file and return an instance of the generated client class."""
        spec = importlib.util.spec_from_file_location(self.class_name, self.path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        client_cls = getattr(module, self.class_name)
        return client_cls(api_key=api_key)

    def __iter__(self) -> Iterator:
        # Backwards compatibility: allows `path, class_name, sd = generate_stub(...)`
        return iter((self.path, self.class_name, self.service_definition))
    
    def __str__(self) -> str:
        return f"FastStub(path={self.path}, class_name={self.class_name}, service_definition={self.service_definition})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def __eq__(self, other: 'FastStub') -> bool:
        return self.path == other.path and self.class_name == other.class_name and self.service_definition == other.service_definition
    
    def __hash__(self) -> int:
        return hash((self.path, self.class_name, self.service_definition))
