from fastsdk.sdk_factory import create_sdk
import sys
import os

from fastsdk import ServiceManager


def test_create_client():
    saved_client_path, class_name, service_definition = create_sdk("test/test_files/face2face.json", save_path="test/output/face2face.py")
    # create dynamic import of the new file 
    import importlib.util
    
    # Add project root to path to make imports work
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Import using spec with the returned saved_client_path
    spec = importlib.util.spec_from_file_location(
        "face2face", saved_client_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the class from the module
    face2face = getattr(module, class_name)
    # Create an instance of the class
    # We assign an url to the service definition to use the local service and to be able to init it.
    ServiceManager.update_service(service_definition.id, service_address="http://localhost:8020/", persist_changes=False)
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


if __name__ == "__main__":
    test_create_client()
