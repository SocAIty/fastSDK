from typing import Dict, Union
from abc import ABC, abstractmethod

from fastsdk.web.definitions.server_job_status import ServerJobStatus
from fastsdk.web.definitions.server_response.base_response import BaseJobResponse, SocaityJobResponse, \
    RunpodJobResponse, ReplicateJobResponse, JobProgress
from media_toolkit.utils.file_conversion import media_from_file_result


class ResponseParserStrategy(ABC):
    @abstractmethod
    def can_parse(self, data: Dict) -> bool:
        """Check if this strategy can parse the given data."""
        pass

    @abstractmethod
    def parse(self, data: Dict) -> BaseJobResponse:
        """Parse the data into a BaseJobResponse object."""
        pass

    @staticmethod
    def parse_status_and_progress(data: Dict) -> tuple[ServerJobStatus, JobProgress]:
        """Parse status and progress from response data."""
        status = ServerJobStatus.from_str(data.get("status"))

        # Extract progress data
        progress_value = data.get("progress", 0.0)
        message = data.get("message")

        # Handle nested progress info
        if isinstance(progress_value, dict):
            message = progress_value.get("message", message)
            progress_value = progress_value.get("progress", 0.0)

        # Convert progress to float
        try:
            progress_value = float(progress_value) if progress_value is not None else 0.0
        except (ValueError, TypeError):
            progress_value = 0.0

        # If status is FINISHED, set progress to 100%
        if status == ServerJobStatus.FINISHED:
            progress_value = 1.0

        return status, JobProgress(progress_value, message=message)


class SocaityResponseParser(ResponseParserStrategy):
    def can_parse(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        return (data.get("endpoint_protocol") == "socaity" and
                "id" in data and "status" in data)

    @staticmethod
    def _parse_media_result(result):
        """
        Method checks the results of the job, and converts file results to media-toolkit objects
        """
        if isinstance(result, dict):
            return media_from_file_result(result, allow_reads_from_disk=False, default_return_if_not_file_result=result)
        elif isinstance(result, list):
            return [
                media_from_file_result(r, allow_reads_from_disk=False, default_return_if_not_file_result=r)
                for r in result
            ]
        else:
            return result

    def parse(self, data: Dict) -> SocaityJobResponse:
        status, progress = self.parse_status_and_progress(data)
        result = self._parse_media_result(data.get("result"))

        return SocaityJobResponse(
            id=data["id"],
            status=status,
            progress=progress,
            error=data.get("error"),
            result=result,  # of media files the endpoint request takes care by parsing nested socaity results
            refresh_job_url=data.get("refresh_job_url", f'/status/{data["id"]}'),
            cancel_job_url=data.get("cancel_job_url", f'/cancel/{data["id"]}'),
            created_at=data.get("created_at"),
            execution_started_at=data.get("execution_started_at"),
            execution_finished_at=data.get("execution_finished_at"),
            endpoint_protocol=data.get("endpoint_protocol", None)
        )


class RunpodResponseParser(ResponseParserStrategy):
    def can_parse(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        return (
            "id" in data and
            "status" in data and
            ServerJobStatus.map_runpod_status(data.get("status")) != ServerJobStatus.UNKNOWN
        )

    def parse(self, data: Dict) -> RunpodJobResponse:
        status, progress = self.parse_status_and_progress(data)

        return RunpodJobResponse(
            id=data["id"],
            status=status,
            error=data.get("error"),
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
    def can_parse(self, data: Dict) -> bool:
        urls = data.get("urls", {})
        return urls and "api.replicate.com" in urls.get("get", "")

    def parse(self, data: Dict) -> ReplicateJobResponse:
        status, progress = self.parse_status_and_progress(data)

        # Handle Replicate-specific status edge case
        if status == ServerJobStatus.UNKNOWN:
            if data.get("status_code", 200) == 200 and not data.get("is_error", False):
                status = ServerJobStatus.FINISHED

        urls = data.get("urls", {})
        job_id = data.get("id", "")

        return ReplicateJobResponse(
            id=job_id,
            status=status,
            error=data.get("error"),
            progress=progress,
            result=data.get("output"),
            refresh_job_url=urls.get("get", f"v1/predictions/{job_id}"),
            cancel_job_url=urls.get("cancel", f"v1/predictions/{job_id}/cancel"),
            stream_job_url=urls.get("stream"),
            version=data.get("version"),
            data_removed=data.get("data_removed"),
            logs=data.get("logs"),
            metrics=data.get("metrics"),
            created_at=data.get("created_at"),
            execution_started_at=data.get("started_at"),
            execution_finished_at=data.get("completed_at"),
            endpoint_protocol="replicate"
        )

