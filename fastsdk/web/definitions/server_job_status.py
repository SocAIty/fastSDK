from enum import Enum


class ServerJobStatus(Enum):
    """Unified status enum for jobs across multiple server providers"""
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

    @staticmethod
    def map_runpod_status(status: str) -> 'ServerJobStatus':
        if not status:
            return ServerJobStatus.UNKNOWN

        RUNPOD_STATUS_MAPPINGS = {
            # Runpod mappings
            "IN_QUEUE": ServerJobStatus.QUEUED,
            "IN_PROGRESS": ServerJobStatus.PROCESSING,
            "COMPLETED": ServerJobStatus.FINISHED,
            "FAILED": ServerJobStatus.FAILED,
            "CANCELLED": ServerJobStatus.CANCELLED,
            "TIMED_OUT": ServerJobStatus.TIMEOUT
        }

        return RUNPOD_STATUS_MAPPINGS.get(status, ServerJobStatus.UNKNOWN)

    @staticmethod
    def map_replicate_status(status: str) -> 'ServerJobStatus':
        if not status:
            return ServerJobStatus.UNKNOWN

        REPLICATE_STATUS_MAPPINGS = {
            # Replicate mappings
            "STARTING": ServerJobStatus.QUEUED,
            "BOOTING": ServerJobStatus.PROCESSING,
            "PROCESSING": ServerJobStatus.PROCESSING,
            "SUCCEEDED": ServerJobStatus.FINISHED,
            "FAILED": ServerJobStatus.FAILED,
            "CANCELED": ServerJobStatus.CANCELLED,
        }

        return REPLICATE_STATUS_MAPPINGS.get(status, ServerJobStatus.UNKNOWN)


    @classmethod
    def from_str(cls, status_str: str) -> 'ServerJobStatus':
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
