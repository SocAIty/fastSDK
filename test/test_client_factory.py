import sys
import os

from fastsdk import FastSDK
import importlib.util

fsdk = FastSDK()


def load_created_client(saved_client_path, class_name):
    # Add project root to path to make imports work
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Import using spec with the returned saved_client_path
    spec = importlib.util.spec_from_file_location(class_name, saved_client_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the class from the module
    inst = getattr(module, class_name)
    return inst


def test_fasttaskapi_client():
    saved_client_path, class_name, service_definition = fsdk.create_sdk("test/test_files/face2face.json", save_path="test/output/face2face.py", class_name="face2face")
    # create dynamic import of the new file 
    face2face = load_created_client(saved_client_path, class_name)
    # Create an instance of the class
    # We assign an url to the service definition to use the local service and to be able to init it.
    fsdk.update_service(service_definition.id, service_address="http://localhost:8020/", persist_changes=False)
    f2f = face2face()

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


def test_cog():
    saved_client_path, class_name, service_definition = fsdk.create_sdk("test/test_files/cog_judith.json", save_path="test/output/cog_judith.py", class_name="Judith")
    # create dynamic import of the new file
    cog_judith = load_created_client(saved_client_path, class_name)
    assert cog_judith
    pass


def test_replicate():
    try:
        import replicate
    except ImportError:
        print("Replicate not installed. Test replicate skipped.")
        return

    replicate_api_key = os.getenv("REPLICATE_API_KEY")
    if not replicate_api_key:
        print("Env REPLICATE_API_KEY not set. Test replicate skipped.")
        return

    replicate_client = replicate.Client(api_token=replicate_api_key)
    
    services_to_test = [
        "qwen/qwen-image-edit-plus",
        "flux-kontext-apps/renaissance"
    ]
    for service in services_to_test:
        model = replicate_client.models.get(service)
        print(f"Testing {model.name}...")
        service_def = fsdk.load_service_definition(model.latest_version.openapi_schema)
        model_save_name = model.name.replace("-", "_")
        saved_client_path, class_name, service_definition = fsdk.create_sdk(service_def, save_path=f"test/output/{model_save_name}.py", class_name=model_save_name)
        replicate_model_client = load_created_client(saved_client_path, class_name)
        assert replicate_model_client
    

if __name__ == "__main__":
    test_fasttaskapi_client()
    test_cog()
    test_replicate()
