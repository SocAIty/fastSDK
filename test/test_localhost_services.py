import fastsdk

service_url = "http://localhost:8009"


def test_connect():
    # Use a service directly - no code generation, no files.
    client = fastsdk.connect(service_url)
    job = client.submit_job("/text2voice", text="Hello, world!")
    result = job.wait_for_result()
    assert result is not None
    result.save("test/output/speechcraft.wav")


def test_generate_stub():
    stub = fastsdk.generate_stub(service_url, save_path="test/output/speechcraft.py")
    assert stub.path.endswith("speechcraft.py")
    assert stub.class_name
    assert stub.service_definition is not None

    # use the stub immediately, without a separate import step
    client = stub.client()
    assert client is not None

    # re-running the same generation must not fail (idempotent registration + file overwrite)
    stub2 = fastsdk.generate_stub(service_url, save_path="test/output/speechcraft.py")
    assert stub2.path == stub.path


def test_inspect_and_customize():
    sd = fastsdk.inspect_service(service_url)
    assert sd.endpoints

    stub = fastsdk.generate_stub(sd, save_path="test/output/custom_save_path.py", class_name="CustomService", service_name="custom_service")
    assert stub.class_name == "CustomService"
    assert fastsdk.get_service("custom_service") is not None


if __name__ == "__main__":
    test_connect()
    test_generate_stub()
    test_inspect_and_customize()
