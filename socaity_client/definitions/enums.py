from enum import Enum


class ModelDomainTag(Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    OTHER = "other"


class ModelTag(Enum):
    TEXT2VOICE = "text2voice"
    TEXT2SOUND = "text2sound"
    TEXT2IMG = "text2img"
    TEXT2VIDEO = "text2video"
    VOICE2VOICE = "voice2voice"
    AUDIO2FACE = "audio2face"
    IMAGE2IMAGE = "image2image"
    FACE2FACE = "face2face"
    OTHER = "other"


class EndpointSpecification(Enum):
    SOCAITY = "socaity"  # all servers that support socaity protocol with job queues
    OPENAPI = "openapi"  # for example fastapi servers
    OTHER = "other"  # other servers



