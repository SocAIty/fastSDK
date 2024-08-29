"""
This is a copy of the socaity_router job_result file and JOB_STATUS file.
It mirrors the data structure of the job server_response object of socaity_router.
If the server_response of an endpoint is this structure, the client_api assumes it is interacting with an socaity endpoint.
On that way, we can queue, wait and get the server_response of the job.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, Union


class ServerJobStatus(Enum):
    """
    These status are delivered by the server to indicate the current state of a submitted job to it
    Works with socaity endpoints and runpod endpoints
    """
    QUEUED: str = "QUEUED"  # job was recieved by the server and is waiting there to be processed
    PROCESSING: str = "PROCESSING"
    FINISHED: str = "FINISHED"
    FAILED: str = "FAILED"
    TIMEOUT: str = "TIMEOUT"
    CANCELLED: str = "CANCELLED"
    UNKNOWN: str = "UNKNOWN"  # If the server returns a status which is not in the list

    @staticmethod
    def from_str(status: str):
        if str is None:
            return ServerJobStatus.UNKNOWN

        status = status.upper()

        # runpod reparse
        runpod_status_map = {
            "IN_QUEUE": ServerJobStatus.QUEUED,
            "IN_PROGRESS": ServerJobStatus.PROCESSING,
            "COMPLETED": ServerJobStatus.FINISHED,
            "TIMED_OUT": ServerJobStatus.TIMEOUT,
        }
        if status in runpod_status_map:
            return runpod_status_map[status]

        # else it should be an ordinary status
        try:
            return ServerJobStatus(status)
        except Exception as e:
            return ServerJobStatus.UNKNOWN


class FileResult:
    file_name: str
    content_type: str
    content: str  # base64 encoded


@dataclass
class ServerJobResponse:
    # Main fields
    id: str
    status: ServerJobStatus
    message: Optional[str] = None  # message deals as error message if ServerJobStatus.FAILED
    result: Union[FileResult, Any, None] = None  # result of the job
    refresh_job_url: Optional[str] = None  # this field is an url where the client can get job status updates

    # this field is used to signal the client that the job is a socaity job / he's interacting with a socaity server
    endpoint_protocol: Optional[str] = "socaity"

    # timestamps socaity
    created_at: Optional[str] = None  # timestamp when the job was created on the server
    execution_started_at: Optional[str] = None  # timestamp when worker started execution
    execution_finished_at: Optional[str] = None  # timestamp when worker finished execution

    # timestamps runpod
    delayTime: Optional[int] = None  # cold start time + queuetime before a worker picks it up.
    execution_time: Optional[int] = None
    retries: Optional[int] = None  # how often runpod tried to get the result of the serverless deployment

    @staticmethod
    def from_dict(data: dict):
        # init basic server job response
        status = ServerJobStatus.from_str(data.get("status", None))
        sjr = ServerJobResponse(id=data.get('id'), status=status)

        # fill in and reparse fields
        sjr.message = data.get("message", None)
        sjr.result = data.get("result", None)

        sjr.endpoint_protocol = data.get("endpoint_protocol", "socaity")
        sjr.created_at = data.get("created_at", None)
        sjr.execution_started_at = data.get("execution_started_at", None)
        sjr.execution_finished_at = data.get("execution_finished_at", None)

        # runpod specifics
        sjr.refresh_job_url = data.get("refresh_job_url", f'/status/{sjr.id}')
        runpod_error = data.get("error", None)
        if runpod_error is not None:
            sjr.message = runpod_error
        sjr.delayTime = data.get("delayTime", None)
        sjr.execution_time = data.get("execution_time", None)
        sjr.retries = data.get("retries", None)

        return sjr



