from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict, Union, Literal
from datetime import datetime

# Literals for domain tags
ModelDomain = Literal["text", "audio", "image", "video", "other"]


# Literals for service specifications
ServiceSpecification = Literal[
    "socaity",      # all socaity.ai endpoints that support fasttaskapi protocol
    "fasttaskapi",  # all servers that support fasttaskapi protocol with job queues
    "runpod",       # for example runpod servers
    "cog",         # is a service protocol used by replicate.ai
    "cog2",        # new cog format with Input/Output schemas
    "replicate",   # a cog service becomes a replicate service when deployed on replicate.ai
    "openai",      # openai endpoints. Specification of chatgpt, etc.
    "openapi",     # servers that support openapi specification
    "other"        # other servers
]

# Literals for parameter locations
ParameterLocation = Literal["query", "path", "header", "cookie", "body"]

# Literals for parameter types
ParameterType = Literal["string", "number", "integer", "boolean", "object", "array", "null"]

ParameterFormat = Literal[
    "file", "image", "video", "audio",  # media-toolkit specific
    "uri", "binary"
]


class ParameterDefinition(BaseModel):
    type: Optional[ParameterType] = Field(default="string")
    format: Union[ParameterFormat, str, None] = None
    enum: Optional[List[Any]] = None  # list of allowed values
    minLength: Optional[int] = None  # minimum length for strings/arrays
    maxLength: Optional[int] = None  # maximum length for strings/arrays
    minimum: Optional[Union[int, float]] = None  # minimum value for numbers
    maximum: Optional[Union[int, float]] = None  # maximum value for numbers
    additional_properties: Optional[Union[bool, Dict[str, Any]]] = None  # for object types, whether additional properties are allowed


class ServiceAddress(BaseModel):
    url: str


class ReplicateServiceAddress(ServiceAddress):
    model_name: Optional[str] = Field(default=None)
    version: Optional[str] = Field(default=None)


class RunpodServiceAddress(ServiceAddress):
    pod_id: str
    path: str


class SocaityServiceAddress(ServiceAddress):
    pass


class EndpointParameter(BaseModel):
    name: str
    # We merge any_of, one_of, all_of into a single definition; if it returns an array, we assume a "any_of" type.
    definition: Optional[Union[ParameterDefinition, List[ParameterDefinition]]] = None
    required: bool = False
    default: Optional[Any] = None
    location: ParameterLocation
    param_schema: Optional[Dict[str, Any]] = None  # the full schema for other parsers to use.
    description: Optional[str] = None


class Meta(BaseModel):
    id: Optional[str] = Field(default=None)
    display_name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    short_desc: Optional[str] = Field(default=None)


class EndpointDefinition(Meta):
    path: str
    parameters: List[EndpointParameter] = Field(default_factory=list)
    responses: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    x_timeout_s: Optional[float] = Field(default=None)  # gives the client a hint how long the request might take
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] = Field(default="GET")


class ModelDefinition(Meta):
    author: Optional[str] = None
    license: Optional[str] = None
    paper_url: Optional[str] = None

    
class ServiceCategory(Meta):
    input_domain: Optional[List[ModelDomain]] = None
    output_domain: Optional[List[ModelDomain]] = None

    
#  A bundle of servicessthat are related to the same model is called a ServiceFamily
#  For example FluxSchnell is a text2image model, but it might be hosted with different services. Running on azure, runpod, replicate etc.
#  But the capabilities of all these services just differ in details. The basic functionality is a text2image model.
#  Thus we would create one ServiceFamily for all FluxSchnell services.
class ServiceFamily(Meta):
    pass


class ServiceDefinition(Meta):
    endpoints: List[EndpointDefinition] = Field(default_factory=list)
    specification: ServiceSpecification = "other"  # Default specification
    used_models: Optional[List[ModelDefinition]] = None  # base models .pth like llama4
    category: Optional[List[str]] = None  # references to service categories
    family_id: Optional[str] = None  # id of the service family this service belongs to
    service_address: Union[ServiceAddress, ReplicateServiceAddress, RunpodServiceAddress, SocaityServiceAddress] = None
    created_at: Optional[Union[datetime, str]] = None  # date and time of creation in utc timezone
    version: Optional[str] = None  # hash of the openapi specification
    full_schema: Optional[Dict[str, Any]] = None  # e.g. raw OpenAPI or Cog schema. If used by other parser.
