from enum import Enum


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
