"""
This is a copy of the socaity_router job_result file and JOB_STATUS file.
It mirrors the data structure of the job server_response object of socaity_router.
If the server_response of an endpoint is this structure, the client_api assumes it is interacting with an socaity endpoint.
On that way, we can queue, wait and get the server_response of the job.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, Union


class SocaityServerJobStatus(Enum):
    """
    These status are delivered by the server to indicate the current state of a submitted job to it
    If a job was send to a socaity server, with the job endpoint and the jobid, the server will return the status
    """
    QUEUED = "Queued"  # job was recieved by the server and is waiting there to be processed
    PROCESSING = "Processing"
    FINISHED = "Finished"
    FAILED = "Failed"
    TIMEOUT = "Timeout"


class FileResult:
    file_name: str
    content_type: str
    content: str  # base64 encoded


@dataclass
class SocaityServerResponse:
    """
    When the user (client) sends a request to a socaity Endpoint, a Job is created on the server.
    The Server returns a json with the following information about the job status on the server.
    """
    id: str
    status: SocaityServerJobStatus
    progress: Optional[float] = 0.0
    message: Optional[str] = None
    result: Union[FileResult, Any, None] = None

    created_at: Optional[str] = None
    queued_at: Optional[str] = None
    execution_started_at: Optional[str] = None
    execution_finished_at: Optional[str] = None

    # this field is used to signal the client that the job is a socaity job / he's interacting with a socaity server
    endpoint_protocol: Optional[str] = "socaity"
    # this field is an url where the client can get job status updates
    refresh_job_url: Optional[str] = None
