from socaity_client.definitions.ai_model import AIModelDescription
from socaity_client.definitions.enums import ModelDomainTag, ModelTag
from socaity_client.web.service_client import ServiceClient
from socaity_client import UploadFile, ImageFile, AudioFile, VideoFile


srvc_fries_maker = ServiceClient(
    service_url="localhost:8000/api",
    model_description=AIModelDescription(
        model_name="FriesMaker",
        model_domain_tags=[ModelDomainTag.IMAGE, ModelDomainTag.AUDIO],
        model_tags=ModelTag.OTHER,
        model_description="This service is used to make fries. This is the test service of the socaity_router."
    )
)
srvc_fries_maker.add_endpoint(endpoint_route="make_fries", post_params={"fries_name": str, "amount": int})
srvc_fries_maker.add_endpoint(
    endpoint_route="make_file_fries",
    file_params={"potato_one": UploadFile, "potato_two": UploadFile, "potato_three": UploadFile}
)
srvc_fries_maker.add_endpoint(endpoint_route="make_image_fries", file_params={"potato_one": ImageFile})
srvc_fries_maker.add_endpoint(endpoint_route="make_audio_fries", file_params={"potato_one": AudioFile, "potato_two": AudioFile})
srvc_fries_maker.add_endpoint(endpoint_route="make_video_fries", file_params={"potato_one": VideoFile, "potato_two": VideoFile})

