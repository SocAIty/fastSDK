from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from fastsdk.web.definitions.socaity_server_response import SocaityServerJobStatus


class RunpodEndpointStatus(Enum):
    """
    These status are delivered by the server to indicate the current state of a submitted job to it
    If a job was send to a socaity server, with the job endpoint and the jobid, the server will return the status
    """
    QUEUED = "IN_QUEUE"  # job was recieved by the server and is waiting there to be processed
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "Failed"
    TIMEOUT = "Timeout"

@dataclass
class RunpodServerResponse:
    id: str
    status: SocaityServerJobStatus
    output: Optional[Any] = None
    error: Optional[str] = None
