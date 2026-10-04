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
    service = fastsdk.inspect_service("test/test_files/cog_judith.json")
    assert service is not None
    assert service_contract_endpoints(service)


def service_contract_endpoints(service) -> bool:
    details = service.details[0] if service.details else None
    return bool(details and details.contract and details.contract.endpoints)


def create_replicate_client(model_name: str) -> FastClient:
    return fastsdk.connect(f"replicate:{model_name}")


def test_create_clients():
    for service in ("qwen/qwen-image-edit-plus", "bytedance/seedream-4.5"):
        assert create_replicate_client(service)


def test_replicate_connect():
    client = fastsdk.connect("replicate:black-forest-labs/flux-schnell")
    assert client.service.details[0].deployment.provider == "replicate"


def test_replicate_cancel():
    client = create_replicate_client("google/veo-3-fast")
    job = client.submit_job(
        "/predictions",
        prompt="A beautiful sunset over a calm ocean.",
        image="https://wallpapercave.com/wp/wp2225992.jpg",
        negative_prompt="monkey",
        duration=4,
        resolution="720p",
        aspect_ratio="16:9",
        generate_audio=False,
    )
    assert job
    sleep(0.5)
    job.cancel(wait=True)
    assert job.is_terminal
    assert job.termination_state.name == "CANCELLED"


def test_replicate_execution_default_params():
    client = fastsdk.connect(
        "victor-upmeet/whisperx:655845d6190ef70573c669245f245892cd039df4b880a1e3a65852c09252f5cc"
    )
    audio_file = AudioFile().from_any("test/test_files/test_audio.wav")
    job = client.submit_job("/predictions", audio_file=audio_file)
    result = job.wait_for_result()
    assert result
    print(result)


if __name__ == "__main__":
    test_cog()
    test_create_clients()
    test_replicate_connect()
    test_replicate_execution_default_params()
    test_replicate_cancel()
