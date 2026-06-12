from .fastStub import GeneratedStub
from media_toolkit import MediaFile, ImageFile, VideoFile, AudioFile
from meseex import gather_results, gather_results_async

from .api import (
    connect,
    inspect_service,
    generate_stub,
    register_service,
    get_service,
    list_services,
    remove_service,
)
from .sdk_factory import create_sdk  # create_sdk is a deprecated alias of generate_stub
from .service_interaction.api_seex import APISeex
from .fastClient import FastClient
from .fastSDK import FastSDK


__all__ = [
    # primary API
    'connect', 'inspect_service', 'generate_stub', 'register_service',
    'get_service', 'list_services', 'remove_service',
    # classes
    'GeneratedStub', 'FastClient', 'APISeex', 'FastSDK',
    # deprecated
    'create_sdk',
    # re-exports
    'MediaFile', 'ImageFile', 'VideoFile', 'AudioFile', 'gather_results', 'gather_results_async'
]
