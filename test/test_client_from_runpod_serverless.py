from fastsdk import FastSDK
import os
from time import sleep
from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk import ServiceAddress


pod_id = "454y79ac0344xv"
serverless_url = f"https://api.runpod.ai/v2/{pod_id}"


def test_async_openapi_spec_fetching():
    fsdk = FastSDK()
    openapi_spec_job = fsdk.load_openapi_spec_from_runpod(serverless_url + "/openapi.json", api_key=os.getenv("RUNPOD_API_KEY"), return_api_job=True)
    openapi_spec = openapi_spec_job.wait_for_result()
    assert isinstance(openapi_spec, dict)
    assert "apipod" in openapi_spec["info"]
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


def get_permanent_client():
    FastSDK().add_service(
        spec_source="test/test_files/face2face.json", 
        service_id="face2face", specification="runpod", 
        service_address=ServiceAddress(url=serverless_url),
    )
    from output.face2face import face2face
    client = face2face(api_key=os.getenv("RUNPOD_API_KEY"))
    return client


def test_job_cancel_immediate():
    client = get_permanent_client()

    print("\n--- Starting Job Cancellation Tests ---")
    print("\n[Test 1] Immediate local cancel...")
    job1 = client.submit_job("/swap-img-to-img", source_img="test/test_files/test_face_1.jpg", target_img="test/test_files/test_face_2.jpg", enhance_face_model=None)
    cancel_info1 = job1.cancel(wait=True)
    print(f"Cancel info status: {getattr(cancel_info1, 'status', 'N/A')}")
    assert job1.termination_state.name == "CANCELLED"
    try:
        job1.get_result()
        assert False, "Should have raised TaskCancelledException"
    except Exception as e:
        print(f"Caught expected exception: {type(e).__name__}: {e}")
        assert e.message == 'Cancelled before remote job submission' 
        assert "cancelled" in str(e).lower()


def test_job_cancel_non_blocking():
    client = get_permanent_client()

    print("\n[Test 2] Non-blocking cancel...")
    job2 = client.submit_job("/swap-img-to-img", source_img="test/test_files/test_face_1.jpg", target_img="test/test_files/test_face_2.jpg", enhance_face_model=None)
    # Wait a tiny bit to ensure it might have started sending but likely still in local tasks or just sent
    sleep(5)
    cancel_info2 = job2.cancel(wait=False)
    print(f"Non-blocking cancel returned immediately. Job terminal: {job2.is_terminal}")
    # It might be terminal already if it was still local, or pending remote cancel
    job2.wait_for_result(timeout_s=10, default_value_on_error="cancelled_fallback")
    print(f"Job 2 final state: {job2.termination_state}")
    assert job2.termination_state.name == "CANCELLED"


def test_job_cancel_remote():
    client = get_permanent_client()
    print("\n[Test 3] Remote cancel (queued on server)...")
    job3 = client.swap_video(faces="test/test_files/test_face_1.jpg", target_video="test/test_files/test_video_short.mp4", enhance_face_model=None)
    # Wait for it to definitely reach the server and get a job ID
    print("Waiting for job to reach server...")
    max_retries = 500
    
    # Check if job has response and id, and status is not unknown/None
    while max_retries > 0:
        if job3.response and job3.response.id and job3.response.status in [APIJobStatus.PROCESSING]:
            break
        sleep(0.1)
        max_retries -= 1
    
    if max_retries == 0:
        print("Warning: Job did not reach server in time for remote cancel test")
    else:
        print(f"Job reached server. ID: {job3.response.id}. Requesting cancel...")
        cancel_info3 = job3.cancel(wait=True)
        print(f"Remote cancel info status: {getattr(cancel_info3, 'status', 'N/A')}")
        assert job3.termination_state.name == "CANCELLED"
        assert cancel_info3.status.name == "CANCELLED"



    
if __name__ == "__main__":
   #test_async_openapi_spec_fetching()
   #test_temporary_auto_client()
   #test_permanent_client()
   #test_job_cancel_immediate()
   #test_job_cancel_non_blocking()
   test_job_cancel_remote()
