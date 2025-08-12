from fastsdk import FastSDK
import os

pod_id = "8oc5gef3sflrc3"
serverless_url = f"https://api.runpod.ai/v2/{pod_id}"


def test_async_openapi_spec_fetching():
    fsdk = FastSDK()
    openapi_spec_job = fsdk.load_openapi_spec_from_runpod(serverless_url + "/openapi.json", api_key=os.getenv("RUNPOD_API_KEY"), return_api_job=True)
    openapi_spec = openapi_spec_job.wait_for_result()
    assert isinstance(openapi_spec, dict)
    assert "fast-task-api" in openapi_spec["info"]
    return openapi_spec
    

def test_temporary_auto_client():
    fsdk = FastSDK()
    client = fsdk.create_temporary_client(serverless_url)
    source_img = "test/test_files/test_face_1.jpg"
    target_img = "test/test_files/test_face_2.jpg"
    response = client.submit_job("/swap-img-to-img", source_img=source_img, target_img=target_img, enhance_face_model=None)
    result = response.wait_for_result()
    assert result is not None
    result.save("test/output/test_face_1_swapped.jpg")


def test_permanent_client():
    fsdk = FastSDK()
    client_sp = fsdk.create_sdk(serverless_url, "test/output/face2face.py")
    assert client_sp is not None
    

if __name__ == "__main__":
    test_async_openapi_spec_fetching()
    test_temporary_auto_client()
    test_permanent_client()
