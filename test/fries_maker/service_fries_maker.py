from typing import List

from fastsdk.definitions.ai_model import AIModelDescription
from fastsdk.definitions.enums import ModelDomainTag
from fastsdk.web.api_client import APIClient
from fastsdk import MediaFile, ImageFile, AudioFile, VideoFile


srvc_fries_maker = APIClient(
    service_name="fries_maker",
    service_urls={
        "local": "localhost:8000/api",
        "runpod_local": "localhost:8000/run"
    }
)

srvc_fries_maker.add_endpoint(
    endpoint_route="test_single_file_upload",
    file_params={"file1": ImageFile}
)

srvc_fries_maker.add_endpoint(
    endpoint_route="mixed_media",
    query_params={
        "anint2": int,
        "astring": str,
        "anint": int,
        "a_base_model": dict
    },
    file_params={
        "anyfile1": MediaFile,
        "anyfile2": ImageFile,
        "anyfile3": MediaFile,
        "img": ImageFile,
        "audio": AudioFile,
        "video": VideoFile,
        "anyfiles": List[MediaFile],
        "anyImages": List[ImageFile],
    }
)


