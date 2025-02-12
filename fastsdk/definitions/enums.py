from enum import Enum


class ModelDomainTag(Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    MISC = "other"


class EndpointSpecification(Enum):
    SOCAITY = "socaity"  # all socaity.ai endpoints that support socaity protocol
    FASTTASKAPI = "fasttaskapi"  # all servers that support socaity protocol with job queues
    RUNPOD = "runpod"  # for example runpod servers
    REPLICATE = "replicate"
    OPENAPI = "openapi"  # for example fastapi servers
    OTHER = "other"  # other servers

