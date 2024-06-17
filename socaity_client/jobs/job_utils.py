import time
from typing import Union, List

from tqdm import tqdm

from socaity_client.jobs.threaded.internal_job import InternalJob
from socaity_client.jobs.threaded.job_status import JOB_STATUS
from socaity_client.utils import flatten_list


def gather_generator(jobs: Union[List[InternalJob], List[InternalJob], InternalJob, list]):
    if not isinstance(jobs, list):
        jobs = [jobs]

    # flatten array
    jobs: List[InternalJob] = list(flatten_list(jobs))
    # start jobs that not have been started
    for job in jobs:
        if job.status == JOB_STATUS.CREATED:
            job.run()

    # with progress bar
    pbar_total = tqdm(total=len(jobs))
    finished_jobs = []
    while len(jobs) > len(finished_jobs):
        for i, job in enumerate(jobs):
            if job.finished() and job not in finished_jobs:
                finished_jobs.append(job)
                yield job
        # update progress bar
        pbar_total.update(len(finished_jobs))
        # give the cpu a break
        time.sleep(0.1)

    pbar_total.close()


def gather_results(jobs: Union[List[InternalJob], List[InternalJob], InternalJob, list]):
    return list(gather_generator(jobs))
