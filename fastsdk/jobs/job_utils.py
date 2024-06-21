import time
from typing import Union, List

from tqdm import tqdm

from fastsdk.jobs.threaded.internal_job import InternalJob
from fastsdk.jobs.threaded.job_status import JOB_STATUS
from fastsdk.utils import flatten_list


def gather_generator(jobs: Union[List[InternalJob], List[List[InternalJob]], InternalJob, list]):
    """
    Generator that yields the results of the jobs once they are completed. Runs until all jobs are completed.
    :param jobs: List of jobs or a single job
    """
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


def gather_results(jobs: Union[List[InternalJob], List[InternalJob], InternalJob, list]) -> List[InternalJob]:
    """
    Waits until all jobs are finished and returns a list of the completed jobs.
    """
    return list(gather_generator(jobs))


def get_job_result(job: InternalJob, print_progress: bool = False, throw_error: bool = True):
    """
    Waits until the job is finished and returns it server_response.
    """
    return job.get_result(print_progress=print_progress, throw_error=throw_error)
