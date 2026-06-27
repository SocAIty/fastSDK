"""
Integration tests for the APIPod schema debug service (``apipod/test/debug_test_services.py``).

The service exposes every OpenAI-compatible APIPod request schema plus raw / typed / none
response-mapping variants. Point it at whichever launch configuration you are exercising:

    cd ../apipod && python test/debug_test_services.py   # launch_schemas(), default :8000
    apipod simulate serverless                           # job queue emulation
    apipod simulate dedicated                          # sync dedicated compute
    apipod simulate serverless-runpod                  # RunPod routing emulation

Set ``APIPOD_DEBUG_TEST_SERVICE_URL`` when the service listens elsewhere (other host,
port or tunnel). fastSDK uses the same ``submit_job()`` + ``wait_for_result()`` path for
sync and job-queue backends; ``specification="apipod"`` ensures polling when the service
returns a job handle.
"""
import os

import fastsdk

DEFAULT_SERVICE_URL = "http://localhost:8000"
service_url = os.environ.get("APIPOD_DEBUG_TEST_SERVICE_URL", DEFAULT_SERVICE_URL)
output_dir = "test/output/apipod_debug"

# Parsed OpenAPI may classify this service as fasttaskapi (FileModel schemas). Force apipod
# so job-based launch configurations poll correctly.
_CONNECT_KWARGS = {"specification": "apipod"}


def _client():
    api_key = os.environ.get("APIPOD_DEBUG_TEST_SERVICE_API_KEY")
    return fastsdk.connect(service_url, api_key=api_key, **_CONNECT_KWARGS)


def _choice_message(result: dict) -> str:
    return result["choices"][0]["message"]["content"]

def test_connect_chat_extended():
    client = _client()
    job = client.submit_job(
        "/schemas/chat-extended",
        messages=[{"role": "user", "content": "ahoy"}],
        persona="captain",
    )
    result = job.wait_for_result()
    assert _choice_message(result) == "[captain] ahoy"


def test_connect_response_mapping_variants():
    """Raw / typed / none endpoints normalize into the same response schemas."""
    client = _client()
    chat_payload = {"messages": [{"role": "user", "content": "hi"}]}

    raw = client.submit_job("/schemas/chat-raw", **chat_payload).wait_for_result()
    assert raw["object"] == "chat.completion"
    assert _choice_message(raw) == "hello there"

    typed = client.submit_job("/schemas/chat-typed", **chat_payload).wait_for_result()
    assert typed["object"] == "chat.completion"
    assert _choice_message(typed) == "hello there"

    completion = client.submit_job("/schemas/completion-raw", prompt="hi").wait_for_result()
    assert completion["object"] == "text_completion"
    assert completion["choices"][0]["text"] == "completed"

    embedding = client.submit_job("/schemas/embedding-raw", input="hi").wait_for_result()
    assert embedding["object"] == "list"
    assert embedding["data"][0]["embedding"] == [0.1, 0.2, 0.3]


def test_connect():
    client = _client()
    job = client.submit_job(
        "/schemas/chat-extended",
        messages=[{"role": "user", "content": "ping"}],
    )
    result = job.wait_for_result()
    assert result is not None
    assert "[pirate] ping" in _choice_message(result)


def test_generate_stub():
    os.makedirs(output_dir, exist_ok=True)
    stub_path = f"{output_dir}/apipod_debug.py"

    stub = fastsdk.generate_stub(service_url, save_path=stub_path, **_CONNECT_KWARGS)
    assert stub.path.endswith("apipod_debug.py")
    assert stub.class_name
    assert stub.service_definition is not None

    client = stub.client()
    assert client is not None

    stub2 = fastsdk.generate_stub(service_url, save_path=stub_path, **_CONNECT_KWARGS)
    assert stub2.path == stub.path


def test_inspect_and_customize():
    sd = fastsdk.inspect_service(service_url)
    assert sd.endpoints

    stub = fastsdk.generate_stub(
        sd,
        save_path=f"{output_dir}/custom_apipod_debug.py",
        class_name="ApipodDebugClient",
        service_name="apipod_debug_test",
        **_CONNECT_KWARGS,
    )
    assert stub.class_name == "ApipodDebugClient"
    assert fastsdk.get_service("apipod_debug_test") is not None


if __name__ == "__main__":
    test_connect_chat_extended()
    test_connect_response_mapping_variants()
    test_connect()
    test_generate_stub()
    test_inspect_and_customize()
