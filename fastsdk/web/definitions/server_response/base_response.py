from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Union

from fastsdk.web.definitions.server_job_status import ServerJobStatus

@dataclass
class JobProgress:
    progress: float = 0.0
    message: Union[str, None] = None


@dataclass
class FileResult:
    file_name: str
    content_type: str
    content: str  # base64 encoded


@dataclass
class BaseJobResponse:
    id: str
    status: ServerJobStatus
    progress: Union[JobProgress, None] = None
    error: Union[str, None] = None
    result: Union[FileResult, Any, None] = None
    refresh_job_url: Union[str, None] = None
    cancel_job_url: Union[str, None] = None
    endpoint_protocol: Union[str, None] = None

    def update(self, other: Union['BaseJobResponse', dict]):
        if isinstance(other, BaseJobResponse):
            other = other.__dict__
        for key, value in other.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


@dataclass
class SocaityJobResponse(BaseJobResponse):
    created_at: Union[str, None] = None
    execution_started_at: Union[str, None] = None
    execution_finished_at: Union[str, None] = None

    def __post_init__(self):
        if not self.endpoint_protocol:
            self.endpoint_protocol = "socaity"


@dataclass
class RunpodJobResponse(BaseJobResponse):
    delayTime: Union[int, None] = None
    executionTime: Union[int, None] = None
    retries: Union[int, None] = None
    workerId: Union[str, None] = None


@dataclass
class ReplicateJobResponse(BaseJobResponse):
    created_at: Union[str, None] = None
    execution_started_at: Union[str, None] = None
    execution_finished_at: Union[str, None] = None
    metrics: Union[dict[str, Any], None] = None
    stream_job_url: Union[str, None] = None
    version: Union[str, None] = None
    data_removed: Union[bool, None] = None
    logs: Union[str, None] = None

    def _replicate_time_to_datetime(self, time_str: str) -> datetime:
        if "Z" in time_str:
            # Remove trailing 'Z' and truncate nanoseconds to microseconds
            time_str = time_str.rstrip("Z")[:26]
        return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)

    @property
    def execution_time_ms(self) -> Union[int, None]:
        if self.execution_started_at is None or self.execution_finished_at is None:
            return None

        try:
            start = self._replicate_time_to_datetime(self.execution_started_at)
            end = self._replicate_time_to_datetime(self.execution_finished_at)
            diff = end - start
            return diff.microseconds // 1000
        except ValueError:
            return None
