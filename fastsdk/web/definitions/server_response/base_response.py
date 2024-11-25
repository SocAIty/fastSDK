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
    executionTime: Optional[int] = None
    retries: Optional[int] = None
    workerId: Optional[str] = None
    endpoint_protocol: str = None  # If was implemented with fast-task-api this is returned too


@dataclass
class ReplicateJobResponse(BaseJobResponse):
    created_at: Optional[str] = None
    execution_started_at: Optional[str] = None
    execution_finished_at: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    stream_job_url: Optional[str] = None
    version: Optional[str] = None
    data_removed: Optional[bool] = None
    logs: Optional[str] = None
