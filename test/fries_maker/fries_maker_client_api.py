import random
import time
from typing import List, Union

from fastsdk import ImageFile, MediaFile, AudioFile, fastJob
from fastsdk.jobs.threaded.internal_job import InternalJob
from fastsdk import fastSDK
from media_toolkit import VideoFile
import os

from test.fries_maker.service_fries_maker import srvc_fries_maker


@fastSDK(srvc_fries_maker)
class FriesMaker:
    @fastJob
    def _test_single_file_upload(self, job: InternalJob, file1: ImageFile):
        endpoint_request = job.request(endpoint_route="test_single_file_upload", file1=file1)

        # get server_response
        endpoint_request.wait_until_finished()

        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response

    @fastJob
    def test_mixed_media(self,
        job: InternalJob,
        anyfile1: MediaFile, anyfile2: ImageFile, anyfile3: MediaFile,
        img: ImageFile | str | bytes,
        audio: AudioFile,
        video: VideoFile,
        anyfiles: List[MediaFile],
        anint2: int,
        anyImages: List[ImageFile],
        astring: str,
        anint: int
    ):
        endpoint_request = job.request(
            endpoint_route="mixed_media",
            anyfile1=anyfile1, anyfile2=anyfile2, anyfile3=anyfile3,
            img=img, audio=audio, video=video,
            anyfiles=anyfiles,
            anint2=anint2,
            anyImages=anyImages,
            astring=astring,
            anint=anint,
            a_base_model=None
        )

        # get server_response
        endpoint_request.wait_until_finished()

        if endpoint_request.error is not None:
            raise Exception(f"Error in making fries: {endpoint_request.error}")

        return endpoint_request.server_response


def resolve_current_dir(filename: str):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


if __name__ == "__main__":
    fm = FriesMaker()
    # j = fm._test_single_file_upload(file1=ImageFile().from_file("test_media/test_face_1.jpg"))
    # res = j.get_result()
    j = fm.test_mixed_media(
        anyfile1=MediaFile().from_file(resolve_current_dir("test_media/test_face_1.jpg")),
        anyfile2=ImageFile().from_file(resolve_current_dir("test_media/test_face_1.jpg")),
        anyfile3=MediaFile().from_file(resolve_current_dir("test_media/test_face_1.jpg")),
        img=resolve_current_dir("test_media/test_face_1.jpg"),
        audio=AudioFile().from_file(resolve_current_dir("test_media/audio_potato.mp3")),
        video=VideoFile().from_file(resolve_current_dir("test_media/video_potato.mp4")),
        anyfiles=[
            MediaFile().from_file(resolve_current_dir("test_media/test_face_1.jpg")),
            resolve_current_dir("test_media/test_face_2.jpg")
        ],
        anint2=1,
        anyImages=[
            ImageFile().from_file(resolve_current_dir("test_media/test_face_1.jpg")),
            ImageFile().from_file(resolve_current_dir("test_media/test_face_2.jpg"))
        ],
        astring="string",
        anint=2
    )

    res = j.get_result()
    a = 1

