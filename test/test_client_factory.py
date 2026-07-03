import os
from time import sleep

import fastsdk
from fastsdk import FastClient


def test_apipod_client():
    stub = fastsdk.generate_stub("test/test_files/face2face.json", save_path="test/output/face2face.py", class_name="face2face")
    assert stub.class_name == "face2face"

    # We assign an url to the service definition to use the local service and to be able to init it.
    fastsdk.FastSDK().update_service(stub.service_definition.id, service_address="http://localhost:8020/", persist_changes=False)
    f2f = stub.client()

    # check presence of method
    assert hasattr(f2f, "swap_img_to_img")

    job = f2f.swap_img_to_img(
        source_img="test/test_files/test_face_1.jpg",
        target_img="test/test_files/test_face_2.jpg"
    )
    assert job

    result = job.wait_for_result()
    if result:
        result.save("test/output/test_face_1_to_2.jpg")
