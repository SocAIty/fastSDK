from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from socaity_client.jobs.threaded.internal_job import InternalJob

from socaity_client.jobs.threaded.job_status import JOB_STATUS
import threading
import time
from typing import Union

from singleton_decorator import singleton


@singleton
class _InternalJobManager:
    def __init__(self):
        self.queue = []
        self.in_progress = []  # a list of {"job_id": job.id, "thread": t_job, "job": job}
        self.results = []
        self.worker_thread = threading.Thread(target=self.process_jobs_in_background, daemon=True)

    def process_job(self, job: InternalJob):
        job._run()
        # store server_response in results. Necessary in threading because thread itself cannot easily return values
        self.results.append(job)

    def process_jobs_in_background(self):
        while True:
            if len(self.queue) == 0 and len(self.in_progress) == 0:
                time.sleep(2)

            # create new jobs from queue
            for job in self.queue:
                t_job = threading.Thread(target=self.process_job, args=(job,), daemon=True)
                self.in_progress.append({"job_id": job.id, "thread": t_job, "job": job})
                self.queue.remove(job)
                t_job.start()

            # check if jobs are finished
            for job_thread in self.in_progress:
                # remove finished jobs
                if not job_thread["thread"].is_alive():
                    self.in_progress.remove(job_thread)

    def create_job_and_submit(
        self,
        job_function: callable,
        job_params: Union[dict, None],
        request_function: callable = None
    ):
        job = InternalJob(
            job_function=job_function,
            job_params=job_params,
            request_function=request_function
        )
        self.submit(job)

    def submit(self, job: InternalJob):
        job.status = JOB_STATUS.QUEUED
        self.queue.append(job)

        # start worker thread if not already done so
        if not self.worker_thread.is_alive():
            self.worker_thread.start()

    def get_job(self, job_id: str):
        raise NotImplementedError("Implement in subclass")


# for easier export instantiate singleton
InternalJobManager = _InternalJobManager()
