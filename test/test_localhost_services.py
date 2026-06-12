import fastsdk

service_url = "http://localhost:8009"


def test_connect():
    # Use a service directly - no code generation, no files.
    client = fastsdk.connect(service_url)
    job = client.submit_job("/text2voice", text="Hello, world!")
    result = job.wait_for_result()
    assert result is not None


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

    stub = fastsdk.generate_stub(sd, save_path="test/output/affe2.py", class_name="Affe", service_name="affe")
    assert stub.class_name == "Affe"
    assert fastsdk.get_service("affe") is not None


if __name__ == "__main__":
    test_connect()
    test_generate_stub()
    test_inspect_and_customize()
