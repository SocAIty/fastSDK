from typing import Dict, Optional, Tuple
from abc import ABC, abstractmethod

from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk.service_interaction.response.base_response import (
    BaseJobResponse, SocaityJobResponse,
    RunpodJobResponse, ReplicateJobResponse, FileModel
)
from media_toolkit import media_from_any

_RUNPOD_SPECIFIC_FIELDS = frozenset({"delayTime", "executionTime", "workerId", "retries"})


class ResponseParserStrategy(ABC):
    @abstractmethod
    def can_parse(self, data: Dict) -> bool:
        pass

    @abstractmethod
    def parse(self, data: Dict, parse_media: bool = True) -> BaseJobResponse:
        pass

    @staticmethod
    def parse_status_and_progress(data: Dict) -> Tuple[APIJobStatus, Optional[float], Optional[str]]:
        """Extract status, progress (float) and message from response data."""
        status = APIJobStatus.from_str(data.get("status"))
        progress = data.get("progress")
        message = data.get("message")

        if isinstance(progress, dict):
            message = progress.get("message", message)
            progress = progress.get("progress")

        try:
            progress = float(progress) if progress is not None else None
        except (ValueError, TypeError):
            progress = None

        if status == APIJobStatus.FINISHED:
            progress = 1.0

        return status, progress, message


class SocaityResponseParser(ResponseParserStrategy):
    """Handles both JobSubmissionResponse and JobStatusResponse from the Socaity gateway."""

    def can_parse(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        # Submission response: has job_id + links
        if "job_id" in data and "links" in data:
            return True

        # Status response: has progress and message
        if "progress" in data and "message" in data:
            return True

        return False

    @staticmethod
    def _parse_media_result(result):
        if result is None:
            return result

        if isinstance(result, (dict, FileModel)):
            try:
                return media_from_any(result, allow_reads_from_disk=False)
            except Exception:
                return result
        elif isinstance(result, list):
            return [SocaityResponseParser._parse_media_result(r) for r in result]
        return result

    def parse(self, data: Dict, parse_media: bool = True) -> SocaityJobResponse:
        status, progress, message = self.parse_status_and_progress(data)

        # Submission uses "job_id"; status uses "id"
        job_id = data.get("id") or data.get("job_id")

        # Submission nests URLs under "links"; status responses don't
        links = data.get("links", {})
        refresh_url = links.get("status") or data.get("refresh_job_url")
        cancel_url = links.get("cancel") or data.get("cancel_job_url")

        # If still no URLs, fallback to defaults
        if not refresh_url:
            refresh_url = f"/gateway/v1/status/{job_id}"
        if not cancel_url:
            cancel_url = f"/gateway/v1/cancel/{job_id}"

        result = data.get("result")
        if parse_media:
            result = self._parse_media_result(result)

        return SocaityJobResponse(
            id=job_id,
            status=status,
            progress=progress,
            message=message,
            error=data.get("error"),
            result=result,
            refresh_job_url=refresh_url,
            cancel_job_url=cancel_url,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class RunpodResponseParser(ResponseParserStrategy):
    def can_parse(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        return (
            "id" in data
            and "status" in data
        )

    def parse(self, data: Dict, parse_media: bool = True) -> RunpodJobResponse:
        status, progress, _ = self.parse_status_and_progress(data)

        return RunpodJobResponse(
            id=data["id"],
            status=status,
            error=data.get("error"),
            progress=progress,
            result=data.get("output"),
            refresh_job_url=data.get("refresh_job_url", f'status/{data["id"]}'),
            cancel_job_url=data.get("cancel_job_url", f'cancel/{data["id"]}'),
            delayTime=data.get("delayTime"),
            executionTime=data.get("executionTime"),
            retries=data.get("retries"),
            workerId=data.get("workerId"),
        )


class ReplicateResponseParser(ResponseParserStrategy):
    def can_parse(self, data: Dict) -> bool:
        urls = data.get("urls", {})
        return bool(urls) and "api.replicate.com" in urls.get("get", "")

    def _parse_media_result(self, result):
        if isinstance(result, str) and "https://replicate.delivery" in result:
            try:
                return media_from_any(result, allow_reads_from_disk=False)
            except Exception:
                return result
        elif isinstance(result, list):
            return [self._parse_media_result(m) for m in result]
        elif isinstance(result, dict):
            return {k: self._parse_media_result(v) for k, v in result.items()}
        return result

    def parse(self, data: Dict, parse_media: bool = False) -> ReplicateJobResponse:
        status, progress, _ = self.parse_status_and_progress(data)

        if status == APIJobStatus.UNKNOWN:
            if data.get("status_code", 200) == 200 and not data.get("is_error", False):
                status = APIJobStatus.FINISHED

        urls = data.get("urls", {})
        job_id = data.get("id", "")

        result = data.get("output")
        if parse_media:
            result = self._parse_media_result(result)

        return ReplicateJobResponse(
            id=job_id,
            status=status,
            error=data.get("error"),
            progress=progress,
            result=result,
            refresh_job_url=urls.get("get", f"v1/predictions/{job_id}"),
            cancel_job_url=urls.get("cancel", f"v1/predictions/{job_id}/cancel"),
            stream_job_url=urls.get("stream"),
            model=data.get("model"),
            version=data.get("version"),
            input=data.get("input"),
            source=data.get("source"),
            status_str=data.get("status"),
            data_removed=data.get("data_removed"),
            logs=data.get("logs"),
            metrics=data.get("metrics"),
            created_at=data.get("created_at"),
            execution_started_at=data.get("started_at"),
            execution_finished_at=data.get("completed_at"),
        )
