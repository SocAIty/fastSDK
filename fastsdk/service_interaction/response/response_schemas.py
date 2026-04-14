from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union

from pydantic import BaseModel, computed_field, field_validator, Field


# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------


class StreamingResponse:
    """Sentinel returned when the HTTP response is a Server-Sent Events stream."""

# ---------------------------------------------------------------------------
# Socaity / APIPod
# ---------------------------------------------------------------------------


class FileModel(BaseModel):
    file_name: str
    content_type: str
    content: Union[str, "FileModel", Any] = Field(
        description="URL, base64 string, bytes-like data, or nested FileModel."
    )
    max_size_mb: Optional[int] = None


class JobLinks(BaseModel):
    status: Optional[str] = None
    cancel: Optional[str] = None
    stream: Optional[str] = None


class JobMetrics(BaseModel):
    execution_time_s: Optional[float] = None
    inference_time_s: Optional[float] = None
    platform_queue_time_s: Optional[float] = None
    provider_queue_time_s: Optional[float] = None
    upload_time_s: Optional[float] = None


class SocaityJobResponse(BaseModel):
    job_id: str
    status: Optional[str] = None
    result: Union[FileModel, list[FileModel], list, str, Any, None] = None
    error: Optional[str] = None
    progress: Optional[float] = None
    message: Optional[str] = None
    service: Optional[str] = None
    endpoint: Optional[str] = None
    metrics: Optional[JobMetrics] = None
    links: Optional[JobLinks] = None

    @field_validator("progress", mode="before")
    @classmethod
    def _coerce_progress(cls, v):
        """Handle legacy dict-shaped progress values from the API."""
        if isinstance(v, dict):
            v = v.get("progress")
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Runpod
# ---------------------------------------------------------------------------

class RunpodJobResponse(BaseModel):
    id: str
    status: Optional[str] = None
    output: Any = None
    error: Optional[str] = None
    delayTime: Optional[int] = None
    executionTime: Optional[int] = None
    retries: Optional[int] = None
    workerId: Optional[str] = None


# ---------------------------------------------------------------------------
# Replicate
# ---------------------------------------------------------------------------

class ReplicateUrls(BaseModel):
    web: Optional[str] = None
    cancel: Optional[str] = None
    get: Optional[str] = None
    stream: Optional[str] = None


class ReplicateMetrics(BaseModel):
    predict_time: Optional[float] = None
    total_time: Optional[float] = None


class ReplicateJobResponse(BaseModel):
    id: str
    model: Optional[str] = None
    version: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    output: Any = None
    logs: Optional[str] = None
    error: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metrics: Optional[Union[ReplicateMetrics, dict[str, Any]]] = None
    urls: Optional[ReplicateUrls] = None
    source: Optional[str] = None
    data_removed: Optional[bool] = None

    def _replicate_time_to_datetime(self, time_str: str) -> datetime:
        if "Z" in time_str:
            time_str = time_str.rstrip("Z")[:26]
        return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)

    @computed_field
    @property
    def execution_time_ms(self) -> Optional[int]:
        if self.started_at is None or self.completed_at is None:
            return None
        try:
            start = self._replicate_time_to_datetime(self.started_at)
            end = self._replicate_time_to_datetime(self.completed_at)
            return int((end - start).total_seconds() * 1000)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Type guard tuple — used by job manager / seex for isinstance checks
# ---------------------------------------------------------------------------

JOB_RESPONSE_TYPES = (SocaityJobResponse, RunpodJobResponse, ReplicateJobResponse)
