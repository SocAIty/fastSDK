from fastsdk import FastSDK
import inspect
from pprint import pprint

fastapi_url = "http://localhost:8000"

def test_async_openapi_spec_fetching():
    fsdk = FastSDK()
    openapi_spec_job = fsdk.load_service_definition(fastapi_url + "/openapi.json")
    openapi_spec = openapi_spec_job.full_schema
    assert isinstance(openapi_spec, dict)
    return openapi_spec

def test_temporary_auto_client():
    fsdk = FastSDK()
    client = fsdk.create_temporary_client(fastapi_url)
    source_img = "test/test_files/test_face_1.jpg"
    target_img = "test/test_files/test_face_2.jpg"
    response = client.submit_job("/swap-img-to-img", source_img=source_img, target_img=target_img, enhance_face_model=None)
    result = response.wait_for_result()
    assert result is not None
    result.save("test/output/test_face_1_swapped.jpg")

def test_permanent_client():
    fsdk = FastSDK()
    client_sp = fsdk.create_sdk(fastapi_url, "test/output/face2face.py")
    assert client_sp is not None

def inspect_object(obj, name="object"):
    print(f"{'='*60}")
    print(f"Inspecting: {name}")
    print(f"Type: {type(obj)}")
    print(f"{'='*60}\n")
    
    # Instance attributes
    if hasattr(obj, '__dict__'):
        print("Instance Attributes:")
        pprint(vars(obj))
        print("\n")
    
    # If dict, show contents
    if isinstance(obj, dict):
        print("Dictionary Contents:")
        pprint(obj)
        print("\n")
    
    # All methods
    print("Public Methods:")
    methods = [m for m in dir(obj) if callable(getattr(obj, m)) and not m.startswith('_')]
    for method_name in methods:
        method = getattr(obj, method_name)
        try:
            sig = inspect.signature(method)
            print(f"  {method_name}{sig}")
        except:
            print(f"  {method_name}()")
    print(f"{'='*60}\n")

def test_llm_client():
    fsdk = FastSDK()
    llm_client = fsdk.create_temporary_client(fastapi_url)

    # Submit the job
    response = llm_client.submit_job("/chat", model="Qwen", messages=[{"role":"user","content":"What is the worth of a mortal's life"}], stream=True)

    
    print("="*60)
    print("GETTING RESPONSE DATA")
    print("="*60)
    
    # Method 1: Get the final result (blocks until complete)
    result = response.get_result(timeout_s=30)
    print(f"Result: {result}")
    print("\n")
    
    # Method 2: Wait for result with timeout
    result_with_timeout = response.wait_for_result(timeout_s=30.0)
    print(f"Result with timeout: {result_with_timeout}")
    print("\n")
    
def test_ping_client():
    fsdk = FastSDK()
    llm_client = fsdk.create_temporary_client(fastapi_url)

    response = llm_client.submit_job("/ping")
    result = response.get_result(timeout_s=10)
    print(f"Ping response: {result}")

if __name__ == "__main__":
    # test_async_openapi_spec_fetching()
    test_ping_client()
    test_llm_client()
    # test_temporary_auto_client()
    # test_permanent_client()