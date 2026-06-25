import fastsdk
from fastsdk import FastClient, AudioFile
import os
from time import sleep


try:
    import replicate  # noqa: F401
except ImportError:
    print("Replicate not installed. Test replicate skipped.")

if not os.getenv("REPLICATE_API_KEY"):
    print("Env REPLICATE_API_KEY not set. Test replicate skipped.")


def test_cog():
    stub = fastsdk.generate_stub("test/test_files/cog_judith.json", save_path="test/output/cog_judith.py", class_name="Judith")
    assert stub is not None


def create_replicate_client(model_name: str) -> FastClient:
    # Replicate models are loaded directly from their model reference.
    # Official models use the /v1/models/{owner}/{name}/predictions scheme,
    # community models the /v1/predictions scheme - resolved automatically.
    model_save_name = model_name.split("/")[-1].replace("-", "_")
    stub = fastsdk.generate_stub(
        f"replicate:{model_name}",
        save_path=f"test/output/{model_save_name.replace('.', '_')}.py",
        class_name=model_save_name
    )
    return stub.client()


def test_create_stubs():
    services_to_test = [
        "qwen/qwen-image-edit-plus",
        "bytedance/seedream-4.5"
    ]
    for service in services_to_test:
        replicate_model_client = create_replicate_client(service)
        assert replicate_model_client


def test_replicate_connect():
    """Replicate models also work without code generation via connect()."""
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


def test_replicate_execution_default_params():
    # We will test t
    replicate_model_client = fastsdk.connect("victor-upmeet/whisperx:655845d6190ef70573c669245f245892cd039df4b880a1e3a65852c09252f5cc")
    assert replicate_model_client
    audio_file = AudioFile().from_any("test/test_files/test_audio.wav")
    job = replicate_model_client.submit_job("/predictions", audio_file=audio_file)
    result = job.wait_for_result()
    assert result
    print(result)


if __name__ == "__main__":
    #test_cog()
    #test_create_stubs()
    #test_replicate_connect()
    test_replicate_execution_default_params()
    
    test_replicate_cancel()
