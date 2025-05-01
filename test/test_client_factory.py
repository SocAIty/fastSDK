from fastsdk.client_factory import create_client
import sys
import os


def test_create_client():
    saved_client_path, class_name = create_client("test/test_files/face2face.json", save_path="test/output/face2face.py")
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
    f2f = face2face()

    # check presence of method
    assert hasattr(f2f, "swap_img_to_img")


if __name__ == "__main__":
    test_create_client()
