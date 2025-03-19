import random
import time
from typing import List, Union

from fastsdk import ImageFile, MediaFile, AudioFile
from fastsdk.jobs.threaded.internal_job import InternalJob
from fastsdk import fastSDK

import cv2
import librosa
import numpy as np

from .service_fries_maker import srvc_fries_maker

fries_maker_client_api = fastSDK(srvc_fries_maker)

@fries_maker_client_api.sdk()
class FriesMaker:

    @fries_maker_client_api.job()
    def _make_fries(self, job: InternalJob, fries_name: str, amount: int = 1):
        endpoint_request = job.request(endpoint_route="make_fries", fries_name=fries_name, amount=amount)

        # emulating workload
        time.sleep(random.randint(0, 3))

        # get server_response
        endpoint_request.wait_until_finished()

        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response

    @fries_maker_client_api.job()
    def _make_file_fries(self, job: InternalJob, potato_one: bytes, potato_two: bytes, potato_three: bytes):
        endpoint_request = job.request_sync(
            endpoint_route="make_file_fries", potato_one=potato_one, potato_two=potato_two, potato_three=potato_three
        )

        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response

    @fries_maker_client_api.job()
    def _make_image_fries(self, job: InternalJob, potato_one: bytes):
        endpoint_request = job.request(endpoint_route="make_image_fries", potato_one=potato_one)
        endpoint_request.wait_until_finished()

        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response

    @fries_maker_client_api.job()
    def _make_audio_fries(self, job: InternalJob, potato_one: bytes, potato_two: AudioFile):
        endpoint_request = job.request(
            endpoint_route="make_audio_fries", potato_one=potato_one, potato_two=potato_two
        )
        endpoint_request.wait_until_finished()
        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response

    @fries_maker_client_api.job()
    def _make_video_fries(self, job: InternalJob, potato_one: bytes, potato_two: bytes):
        endpoint_request = job.request_sync(
            endpoint_route="make_video_fries", potato_one=potato_one, potato_two=potato_two
        )

        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response

    def make_fries(self, fries_name: str, amount: int) -> InternalJob:
        return self._make_fries(fries_name, amount)

    def make_file_fries(self, potato_one: str, potato_two: str) -> InternalJob:
        potato_three = potato_two
        # standard python file handle
        potato_one = open(potato_one, "rb")
        # read with cv2
        potato_two = cv2.imread(potato_two)
        return self._make_file_fries(potato_one, potato_two, potato_three)

    def make_image_fries(self, potato_one: Union[str, bytes, np.array, ImageFile, MediaFile]) -> InternalJob:
        """
        Tests upload of standard file types.
        """
        job = self._make_image_fries(potato_one)
        return job


    def make_audio_fries(self, potato_one: str) -> InternalJob:
        """
        Tests upload of standard file types.
        """
        # standard python file handle
        potato_one = open(potato_one, "rb")
        # read with librosa
        potato_two, _sampling_rate = librosa.load(potato_one)

        return self._make_audio_fries(potato_one, potato_two)

    def make_video_fries(self, potato_one: str, potato_two: str) -> List[InternalJob]:
        """
        Tests upload of standard file types.
        """
        # standard python file handle
        potato_one = open(potato_one, "rb")

        # read with cv2
        potato_three = cv2.VideoCapture(potato_two)

        # read file
        with open(potato_two, "rb") as f:
            potato_two = f.read()

        job_files = self._make_video_fries(potato_one, potato_two)
        job_cv2 = self._make_video_fries(potato_one, potato_three)
        return [job_files, job_cv2]