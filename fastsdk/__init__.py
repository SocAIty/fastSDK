from media_toolkit import MediaFile, ImageFile, VideoFile, AudioFile
import importlib

# Import gather utilities from `meseex` robustly to avoid editable-install import ordering issues.
try:
    from meseex import gather_results, gather_results_async
except Exception:
    try:
        mod = importlib.import_module('meseex.gather')
        gather_results = getattr(mod, 'gather_results')
        gather_results_async = getattr(mod, 'gather_results_async')
    except Exception:
        # Provide placeholders to avoid import-time crashes; runtime callers will receive clearer errors.
        def gather_results(*args, **kwargs):
            raise ImportError('meseex.gather_results is not available')

        async def gather_results_async(*args, **kwargs):
            raise ImportError('meseex.gather_results_async is not available')
try:
    from meseex import MeseexBox, MrMeseex
except Exception:
    try:
        mod_box = importlib.import_module('meseex.meseex_box')
        MeseexBox = getattr(mod_box, 'MeseexBox')
        mod_mr = importlib.import_module('meseex.mr_meseex')
        MrMeseex = getattr(mod_mr, 'MrMeseex')
    except Exception:
        # Provide placeholders to avoid import-time crashes; runtime callers will receive clearer errors.
        class MeseexBox:
            def __init__(self, *args, **kwargs):
                raise ImportError('MeseexBox is not available')

        class MrMeseex:
            def __init__(self, *args, **kwargs):
                raise ImportError('MrMeseex is not available')
from .sdk_factory import create_sdk
from .service_interaction.api_job_manager import APISeex
from .fastClient import FastClient

from .service_definition import RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress, ServiceSpecification

from .fastSDK import FastSDK


__all__ = [
    'create_sdk', 'APISeex', 'FastClient', 'FastSDK',
    'MediaFile', 'ImageFile', 'VideoFile', 'AudioFile', 'gather_results', 'gather_results_async',
    'RunpodServiceAddress', 'ReplicateServiceAddress', 'SocaityServiceAddress', 'ServiceSpecification'
]
