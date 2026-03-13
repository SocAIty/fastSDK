from enum import Enum

RUNPOD_STATUS_MAPPINGS = {
    "IN_QUEUE": "QUEUED",
    "IN_PROGRESS": "PROCESSING",
    "COMPLETED": "FINISHED",
    "FAILED": "FAILED",
    "CANCELLED": "CANCELLED",
    "TIMED_OUT": "TIMEOUT",
}

REPLICATE_STATUS_MAPPINGS = {
    "STARTING": "QUEUED",
    "BOOTING": "PROCESSING",
    "PROCESSING": "PROCESSING",
    "SUCCEEDED": "FINISHED",
    "FAILED": "FAILED",
    "CANCELED": "CANCELLED",
    "ABORTED": "CANCELLED",
}


class APIJobStatus(Enum):
    """
    Unified status enum for jobs across multiple server providers.
    Describes the status the job has on the service (server-side).
    """
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

    @staticmethod
    def map_runpod_status(status: str) -> 'APIJobStatus':
        if not status:
            return APIJobStatus.UNKNOWN
        canonical = RUNPOD_STATUS_MAPPINGS.get(status)
        if canonical is None:
            return APIJobStatus.UNKNOWN
        return APIJobStatus(canonical)

    @staticmethod
    def map_replicate_status(status: str) -> 'APIJobStatus':
        if not status:
            return APIJobStatus.UNKNOWN
        canonical = REPLICATE_STATUS_MAPPINGS.get(status)
        if canonical is None:
            return APIJobStatus.UNKNOWN
        return APIJobStatus(canonical)

    @classmethod
    def from_str(cls, status_str: str) -> 'APIJobStatus':
        """Convert any platform's status string to the unified enum."""
        if not status_str:
            return cls.UNKNOWN

        if isinstance(status_str, cls):
            return status_str

        status_str = status_str.upper()

        try:
            return cls(status_str)
        except ValueError:
            pass

        result = cls.map_runpod_status(status_str)
        if result != cls.UNKNOWN:
            return result

        return cls.map_replicate_status(status_str)
