from datetime import datetime, timezone
from typing import Any, Union, Optional
from pydantic import BaseModel, Field, computed_field
from .api_job_status import APIJobStatus


class JobProgress(BaseModel):
    progress: float = Field(default=0.0)
    message: Optional[str] = Field(default=None)


class FileModel(BaseModel):
    file_name: str
    content_type: str
    content: str = Field(description="url or base64 or bytes encoded content")


class BaseJobResponse(BaseModel):
    id: str
    status: APIJobStatus
    progress: Optional[JobProgress] = Field(default=None)
    error: Optional[str] = Field(default=None)
    result: Optional[Union[FileModel, Any]] = Field(default=None)
    refresh_job_url: Optional[str] = Field(default=None)
    cancel_job_url: Optional[str] = Field(default=None)
    service_specification: Optional[str] = None

    def update(self, other: Union['BaseJobResponse', dict]) -> None:
        if isinstance(other, BaseJobResponse):
            other = other.model_dump(exclude_unset=True)
        for key, value in other.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


class SocaityJobResponse(BaseJobResponse):
    created_at: Optional[str] = Field(default=None)
    execution_started_at: Optional[str] = Field(default=None)
    execution_finished_at: Optional[str] = Field(default=None)
    endpoint_protocol: str = Field(default="socaity")


class RunpodJobResponse(BaseJobResponse):
    delayTime: Optional[int] = Field(default=None)
    executionTime: Optional[int] = Field(default=None)
    retries: Optional[int] = Field(default=None)
    workerId: Optional[str] = Field(default=None)


class ReplicateJobResponse(BaseJobResponse):
    created_at: Optional[str] = Field(default=None)
    execution_started_at: Optional[str] = Field(default=None)
    execution_finished_at: Optional[str] = Field(default=None)
    metrics: Optional[dict[str, Any]] = Field(default=None)
    stream_job_url: Optional[str] = Field(default=None)
    version: Optional[str] = Field(default=None)
    data_removed: Optional[bool] = Field(default=None)
    logs: Optional[str] = Field(default=None)

    def _replicate_time_to_datetime(self, time_str: str) -> datetime:
        if "Z" in time_str:
            # Remove trailing 'Z' and truncate nanoseconds to microseconds
            time_str = time_str.rstrip("Z")[:26]
        return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)

    @computed_field
    @property
    def execution_time_ms(self) -> Optional[int]:
        if self.execution_started_at is None or self.execution_finished_at is None:
            return None

        try:
            start = self._replicate_time_to_datetime(self.execution_started_at)
            end = self._replicate_time_to_datetime(self.execution_finished_at)
            diff = end - start
            return diff.microseconds // 1000
        except ValueError:
            return None
