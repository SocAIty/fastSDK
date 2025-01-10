from typing import Dict
from abc import ABC, abstractmethod

from fastsdk.web.definitions.server_job_status import ServerJobStatus
from fastsdk.web.definitions.server_response.base_response import BaseJobResponse, SocaityJobResponse, \
    RunpodJobResponse, ReplicateJobResponse


class ResponseParserStrategy(ABC):
    @abstractmethod
    def can_parse(self, data: Dict) -> bool:
        pass

    @abstractmethod
    def parse(self, data: Dict) -> BaseJobResponse:
        pass


class SocaityResponseParser(ResponseParserStrategy):
    def can_parse(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        return (data.get("endpoint_protocol") == "socaity" and
                "id" in data and "status" in data)

    def parse(self, data: Dict) -> SocaityJobResponse:
        status = ServerJobStatus.from_str(data.get("status"))

        progress = data.get("progress", None)
        progress = float(progress) if progress is not None else 0.0
        if status == ServerJobStatus.FINISHED:
            progress = 1.0

        return SocaityJobResponse(
            id=data["id"],
            status=status,
            message=data.get("message"),
            progress=progress,
            result=data.get("result"),
            refresh_job_url=data.get("refresh_job_url", f'/status/{data["id"]}'),
            cancel_job_url=data.get("cancel_job_url", f'/cancel/{data["id"]}'),
            created_at=data.get("created_at"),
            execution_started_at=data.get("execution_started_at"),
            execution_finished_at=data.get("execution_finished_at"),
            endpoint_protocol=data.get("endpoint_protocol", None)
        )


class RunpodResponseParser(ResponseParserStrategy):
    STATUS_MAP = {
        "IN_QUEUE": ServerJobStatus.QUEUED,
        "IN_PROGRESS": ServerJobStatus.PROCESSING,
        "COMPLETED": ServerJobStatus.FINISHED,
        "FAILED": ServerJobStatus.FAILED,
        "CANCELLED": ServerJobStatus.CANCELLED,
        "TIMED_OUT": ServerJobStatus.TIMEOUT
    }

    def can_parse(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        return ("id" in data and "status" in data and
                data.get("status") in self.STATUS_MAP.keys())

    def parse(self, data: Dict) -> RunpodJobResponse:
        status = self.STATUS_MAP.get(data.get("status", "").upper(), ServerJobStatus.QUEUED)

        progress = data.get("progress", None)
        progress = float(progress) if progress is not None else 0.0
        if status == ServerJobStatus.FINISHED:
            progress = 1.0

        return RunpodJobResponse(
            id=data["id"],
            status=status,
            message=data.get("error"),  # Runpod uses 'error' instead of 'message'
            progress=progress,
            result=data.get("output"),
            refresh_job_url=data.get("refresh_job_url", f'/status/{data["id"]}'),
            cancel_job_url=data.get("cancel_job_url", f'/cancel/{data["id"]}'),
            delayTime=data.get("delayTime", None),
            executionTime=data.get("executionTime", None),
            retries=data.get("retries", None),
            workerId=data.get("workerId", None),
            endpoint_protocol=data.get("endpoint_protocol", None)
        )


class ReplicateResponseParser(ResponseParserStrategy):
    STATUS_MAP = {
        "starting": ServerJobStatus.QUEUED,
        "booting": ServerJobStatus.PROCESSING,
        "processing": ServerJobStatus.PROCESSING,
        "succeeded": ServerJobStatus.FINISHED,
        "failed": ServerJobStatus.FAILED,
        "canceled": ServerJobStatus.CANCELLED,
    }

    def can_parse(self, data: Dict) -> bool:
        urls = data.get("urls", None)
        if urls:
            get = urls.get("get", "")
            if "api.replicate.com" in get:
                return True
        return False

    def parse(self, data: Dict) -> ReplicateJobResponse:
        _id = data.get("id")

        status = data.get("status", None)
        if not status:
            if data.get("status_code", 200) and not data.get("is_error", True):
                status = "succeeded"

        status = self.STATUS_MAP.get(status, ServerJobStatus.QUEUED)

        progress = data.get("progress", None)
        progress = float(progress) if progress is not None else 0.0
        if status == ServerJobStatus.FINISHED:
            progress = 1.0

        urls = data.get("urls", {})
        return ReplicateJobResponse(
            id=_id,
            status=status,
            message=data.get("error"),  # Replicate uses 'error' instead of 'message'
            progress=progress,
            result=data.get("output"),
            refresh_job_url=urls.get("get", f"v1/predictions/{_id}"),
            cancel_job_url=urls.get("cancel", f"v1/predictions/{_id}/cancel"),
            stream_job_url=urls.get("stream", None),
            version=data.get("version", None),
            data_removed=data.get("data_removed", None),
            logs=data.get("logs", None),
            metrics=data.get("metrics", None),
            created_at=data.get("created_at", None),
            execution_started_at=data.get("started_at", None),
            execution_finished_at=data.get("completed_at", None)
        )

