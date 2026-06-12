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


def test_cog():
    stub = fastsdk.generate_stub("test/test_files/cog_judith.json", save_path="test/output/cog_judith.py", class_name="Judith")
    assert stub.client() is not None


def create_replicate_client(model_name: str) -> FastClient:
    try:
        import replicate  # noqa: F401
    except ImportError:
        print("Replicate not installed. Test replicate skipped.")
        return None

    if not os.getenv("REPLICATE_API_KEY"):
        print("Env REPLICATE_API_KEY not set. Test replicate skipped.")
        return None

    # Replicate models are loaded directly from their model reference.
    # Official models use the /v1/models/{owner}/{name}/predictions scheme,
    # community models the /v1/predictions scheme - resolved automatically.
    model_save_name = model_name.split("/")[-1].replace("-", "_")
    stub = fastsdk.generate_stub(
        f"replicate:{model_name}",
        save_path=f"test/output/{model_save_name}.py",
        class_name=model_save_name
    )
    return stub.client()


def test_replicate():
    services_to_test = [
        "qwen/qwen-image-edit-plus",
        "flux-kontext-apps/renaissance"
    ]
    for service in services_to_test:
        replicate_model_client = create_replicate_client(service)
        assert replicate_model_client


def test_replicate_connect():
    """Replicate models also work without code generation via connect()."""
    try:
        import replicate  # noqa: F401
    except ImportError:
        print("Replicate not installed. Test replicate skipped.")
        return
    if not os.getenv("REPLICATE_API_KEY"):
        print("Env REPLICATE_API_KEY not set. Test replicate skipped.")
        return

    client = fastsdk.connect("replicate:black-forest-labs/flux-schnell")
    assert client.service_definition.specification == "replicate"


def test_replicate_cancel():
    replicate_model_client = create_replicate_client("google/veo-3-fast")
    assert replicate_model_client
    job = replicate_model_client(
        prompt="A beautiful sunset over a calm ocean.",
        image="https://wallpapercave.com/wp/wp2225992.jpg",
        negative_prompt="monkey", duration=4, resolution="720p",
        aspect_ratio="16:9",
        generate_audio=False
    )
    assert job
    sleep(0.5)
    job.cancel(wait=True)
    assert job.is_terminal
    assert job.termination_state.name == "CANCELLED"


if __name__ == "__main__":
    # test_apipod_client()
    # test_cog()
    # test_replicate()
    test_replicate_cancel()
