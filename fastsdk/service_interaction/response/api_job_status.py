from enum import Enum


class APIJobStatus(Enum):
    """
    Describes the status the job has on the service (server-side)
    Unified status enum for jobs across multiple server providers
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

        RUNPOD_STATUS_MAPPINGS = {
            # Runpod mappings
            "IN_QUEUE": APIJobStatus.QUEUED,
            "IN_PROGRESS": APIJobStatus.PROCESSING,
            "COMPLETED": APIJobStatus.FINISHED,
            "FAILED": APIJobStatus.FAILED,
            "CANCELLED": APIJobStatus.CANCELLED,
            "TIMED_OUT": APIJobStatus.TIMEOUT
        }

        return RUNPOD_STATUS_MAPPINGS.get(status, APIJobStatus.UNKNOWN)

    @staticmethod
    def map_replicate_status(status: str) -> 'APIJobStatus':
        if not status:
            return APIJobStatus.UNKNOWN

        REPLICATE_STATUS_MAPPINGS = {
            # Replicate mappings
            "STARTING": APIJobStatus.QUEUED,
            "BOOTING": APIJobStatus.PROCESSING,
            "PROCESSING": APIJobStatus.PROCESSING,
            "SUCCEEDED": APIJobStatus.FINISHED,
            "FAILED": APIJobStatus.FAILED,
            "CANCELED": APIJobStatus.CANCELLED,
        }

        return REPLICATE_STATUS_MAPPINGS.get(status, APIJobStatus.UNKNOWN)

    @classmethod
    def from_str(cls, status_str: str) -> 'APIJobStatus':
        """Convert any platform's status string to the unified enum"""
        if not status_str:
            return cls.UNKNOWN

        if isinstance(status_str, cls):
            return status_str

        if isinstance(status_str, str):
            status_str = status_str.upper()

        # Try direct match first
        try:
            return cls(status_str)
        except ValueError:
            # Try mapped values
            x = cls.map_runpod_status(status_str)
            if x is not None and x != cls.UNKNOWN:
                return x
            return cls.map_replicate_status(status_str)
