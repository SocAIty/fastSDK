import os

import fastsdk
from fastsdk.fastClient import FastClient


def register_service_def_local_socaity_backend():
    return fastsdk.register_service(
        "test/test_files/face2face.json",
        service_id="face2face",
        service_address="http://localhost:8001/v1/face2face",
    )


def test_manual_face2face():
    service = register_service_def_local_socaity_backend()
    assert service is not None
    client = FastClient("face2face", api_key=os.getenv("SOCAITY_API_KEY"))
    job = client.submit_job(
        "/swap-img-to-img",
        source_img="test/test_files/test_face_1.jpg",
        target_img="test/test_files/test_face_2.jpg",
    )
    result = job.wait_for_result()
    result.save("test/output/test_face_1_swapped.jpg")


if __name__ == "__main__":
    test_manual_face2face()
