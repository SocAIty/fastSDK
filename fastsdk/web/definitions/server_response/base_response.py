from dataclasses import dataclass
from typing import Union, Optional, Any, Dict

from fastsdk.web.definitions.server_job_status import ServerJobStatus


@dataclass
class FileResult:
    file_name: str
    content_type: str
    content: str  # base64 encoded


@dataclass
class BaseJobResponse:
    id: str
    status: ServerJobStatus
    message: Optional[str] = None
    progress: Optional[float] = None
    result: Union[FileResult, Any, None] = None
    refresh_job_url: Optional[str] = None
    cancel_job_url: Optional[str] = None

    def update(self, other: Union['BaseJobResponse', Dict]):
        if isinstance(other, BaseJobResponse):
            other = other.__dict__
        for key, value in other.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


#@dataclass
#class FastTaskAPIJobResponse(BaseJobResponse):
#    endpoint_protocol: str = "fasttaskapi"
#    created_at: Optional[str] = None
#    execution_started_at: Optional[str] = None
#    execution_finished_at: Optional[str] = None

@dataclass
class SocaityJobResponse(BaseJobResponse):
    endpoint_protocol: str = "socaity"
    created_at: Optional[str] = None
    execution_started_at: Optional[str] = None
    execution_finished_at: Optional[str] = None


@dataclass
class RunpodJobResponse(BaseJobResponse):
    delayTime: Optional[int] = None
    execution_time: Optional[int] = None
    retries: Optional[int] = None
