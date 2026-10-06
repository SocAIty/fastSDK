import fastsdk

service_url = "http://localhost:8009"


def test_connect():
    client = fastsdk.connect(service_url)
    job = client.submit_job("/text2voice", text="Hello, world!")
    result = job.wait_for_result()
    assert result is not None
    result.save("test/output/speechcraft.wav")


def test_inspect():
    sd = fastsdk.inspect_service(service_url)
    assert sd.details[0].contract.endpoints


if __name__ == "__main__":
    test_connect()
    test_inspect()
