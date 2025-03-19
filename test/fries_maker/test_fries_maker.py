from fastsdk import MediaFile, ImageFile
from fastsdk.jobs.job_utils import gather_generator
from .fries_maker_client_api import FriesMaker

import cv2
import base64

# get the media files
test_file_folder = "./test_media/"
img_potato_one = test_file_folder + "potato_one.jpeg"
img_potato_two = test_file_folder + "potato_two.png"
audio_potato = test_file_folder + "audio_potato.mp3"
video_potato = test_file_folder + "video_potato.mp4"


fries_maker = FriesMaker()
fries_maker.start_jobs_immediately = True

count = 0
def test_simple_rpc():
    global count
    count += 1
    easy_job = fries_maker.make_fries(f"super_chilli_fries {count}", count)
    return easy_job

def test_upload_file():
    file_jobs = fries_maker.make_file_fries(img_potato_one, img_potato_two)
    result = file_jobs.wait_for_finished()
    return result

"""
Images: tests upload of standard file types
"""
def test_image_upload():
    # standard python file handle
    potato_handle = open(img_potato_one, "rb")
    job_handle = fries_maker.make_image_fries(potato_handle)
    # read file
    with open(img_potato_one, "rb") as f:
        potato_bytes = f.read()

    job_bytes = fries_maker.make_image_fries(potato_bytes)
    # read with cv2
    potato_cv2 = cv2.imread(img_potato_one)
    job_cv2 = fries_maker.make_image_fries(potato_cv2)
    # as file instance
    upload_file_instance = MediaFile()
    upload_file_instance.from_file(img_potato_two)
    job_upload_file_instance = fries_maker.make_image_fries(upload_file_instance)
    # as image file instance
    img_file_instance = ImageFile()
    img_file_instance.from_bytes(potato_bytes)
    job_img_file_instance = fries_maker.make_image_fries(img_file_instance)
    # as b64
    potato_b64 = base64.b64encode(potato_bytes).decode('utf-8')
    job_b64 = fries_maker.make_image_fries(potato_b64)
    # test one by one
    # res_handle = job_handle.wait_for_finished()
    # res_bytes = job_bytes.wait_for_finished()
    # res_cv2 = job_cv2.wait_for_finished()
    # res_uf = job_upload_file_instance.wait_for_finished()
    # res_if = job_img_file_instance.wait_for_finished()
    # res_b64 = job_b64.wait_for_finished()

    all_jobs = [job_handle, job_bytes, job_cv2, job_upload_file_instance, job_img_file_instance, job_b64]

    return all_jobs


def test_audio_upload():
    audio_job = fries_maker.make_audio_fries(audio_potato).run_sync()
    return audio_job



if __name__ == "__main__":

    #test_simple_rpc()
    #test_image_upload()
    #test_audio_upload()

    # mini stress test
    def stress_test(func, num_iters=10):
        jobs = [func() for i in range(num_iters)]
        for finished_job in gather_generator(jobs):
            print(finished_job.server_response)


    #stress_test(test_simple_rpc, 10)
    stress_test(test_image_upload, 10)
