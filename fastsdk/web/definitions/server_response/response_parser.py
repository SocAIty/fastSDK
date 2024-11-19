from typing import Optional, Any, Union, Dict
from abc import ABC, abstractmethod
import json
import httpx

from fastsdk.web.definitions.server_job_status import ServerJobStatus
from fastsdk.web.definitions.server_response.base_response import BaseJobResponse, SocaityJobResponse, RunpodJobResponse


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
            execution_finished_at=data.get("execution_finished_at")
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

        return RunpodJobResponse(
            id=data["id"],
            status=status,
            message=data.get("error"),  # Runpod uses 'error' instead of 'message'
            progress=progress,
            result=data.get("output"),
            refresh_job_url=data.get("refresh_job_url", f'/status/{data["id"]}'),
            cancel_job_url=data.get("cancel_job_url", f'/cancel/{data["id"]}'),
            delayTime=data.get("delayTime"),
            execution_time=data.get("execution_time"),
            retries=data.get("retries")
        )


class ResponseParser:
    def __init__(self):
        self.strategies = [
            SocaityResponseParser(),
            RunpodResponseParser()
        ]

    def parse_response(self, response: httpx.Response) -> Union[BaseJobResponse, bytes, None]:
        """Parse HTTP response into appropriate response object."""
        if not response:
            return None

        if "application/json" not in response.headers.get("Content-Type", ""):
            return response.content

        try:
            data = response.json()

            # Try each parser strategy
            for strategy in self.strategies:
                if strategy.can_parse(data):
                    parsed_response = strategy.parse(data)

                    # Handle nested Runpod output
                    if isinstance(parsed_response, RunpodJobResponse) and isinstance(parsed_response.result, str):
                        try:
                            nested_data = json.loads(parsed_response.result)
                            if any(strategy.can_parse(nested_data) for strategy in self.strategies):
                                nested_response = self.parse_response(httpx.Response(200, json=nested_data))
                                parsed_response.update(nested_response)
                        except json.JSONDecodeError:
                            pass

                    return parsed_response

            return data  # Return raw JSON if no parser matches

        except json.JSONDecodeError:
            return response.content

    @staticmethod
    def check_response_status(response: httpx.Response) -> Optional[str]:
        """Check HTTP response status code and return error message if applicable."""
        if response.status_code == 200:
            return None

        error_messages = {
            401: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            404: f"Endpoint {response.url} error: not found.",
        }

        if response.status_code in error_messages:
            return error_messages[response.status_code]
        elif response.status_code >= 400:
            return f"Endpoint {response.url} error: {response.content}."

        return None