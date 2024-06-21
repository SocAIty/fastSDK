from enum import Enum


class JOB_STATUS(Enum):
    """
    These status are used to keep track of the job status in the client (internally in the package)
    """
    CREATED = "created"  # job was internally created
    QUEUED = "queued"   # job was added to the internal job queue
    PROCESSING = "processing"  # job is currently processed
    FAILED = "failed"  # internal package error
    REQUEST_TIMEOUT = "request_timeout"  # request took too long
    FINISHED = "finished"
