import json
from typing import Union
import httpx

from fastsdk.web.definitions.socaity_server_response import ServerJobStatus, ServerJobResponse


def is_socaity_server_response(resp_json: dict) -> bool:
    if resp_json is None or not isinstance(resp_json, dict):
        return False

    if "endpoint_protocol" not in resp_json or resp_json["endpoint_protocol"] != "socaity":
        return False

    required_fields = ["id", "status"]
    return all(field in resp_json for field in required_fields)


def is_runpod_server_response(json: dict) -> bool:
    if "id" in json and "status" in json:
        if json["status"] in ["IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]:
            return True
    return False


def runpod_status_to_socaity_status(status: str) -> ServerJobStatus:
    if status is None:
        return ServerJobStatus.QUEUED

    runpod_status_map = {
        "IN_QUEUE": ServerJobStatus.QUEUED,
        "IN_PROGRESS": ServerJobStatus.PROCESSING,
        "COMPLETED": ServerJobStatus.FINISHED,
        "FAILED": ServerJobStatus.FAILED,
        "CANCELLED": ServerJobStatus.CANCELLED,
        "TIMED_OUT": ServerJobStatus.TIMEOUT
    }
    st = status.upper()
    if st in runpod_status_map:
        return runpod_status_map[st]
    return ServerJobStatus.QUEUED


def parse_response(response: httpx.Response) -> Union[ServerJobResponse, bytes, dict, object]:
    """
    Parses the response of a request.
    :param response: The response of the request either formatted as resp_json or the raw _content_buffer
    :return: The parsed response as SocaityServerResponse or the raw _content_buffer.
    """
    if response is None:
        return None

    if hasattr(response, 'headers') and "application/json" in response.headers.get("Content-Type", ""):
        rjson = response.json()

        if is_socaity_server_response(rjson):
            return ServerJobResponse.from_dict(rjson)

        # any other resp_json response from the server
        if not is_runpod_server_response(rjson):
            return rjson

        # parse runpod response
        # if implemented with fast-task-api the output will have socaity like structure
        parsed_result = ServerJobResponse.from_dict(rjson)
        runpod_output = rjson.get("output", None)
        # if running in serverless mode, the output is a "string" that is formed as resp_json.
        # or a gzip file with the required information
        if isinstance(runpod_output, str):
            try:
                runpod_output = json.loads(runpod_output)
            except ValueError as e:
                pass

        if is_socaity_server_response(runpod_output):
            parsed_socaity_result = ServerJobResponse.from_dict(runpod_output)
            parsed_result.update(parsed_socaity_result)
        else:
            parsed_result.result = runpod_output

        return parsed_result
    else:
        # whatever the endpoint returns
        return response.content


def has_request_status_code_error(response: httpx.Response) -> Union[str, bool]:
    """
    Parses the status code of a response.
    :param response: The response of the request.
    :return: an error message if there was an error, otherwise False.
    """
    if response.status_code == 200:
        return False
    elif response.status_code == 401:
        return f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?"
    elif response.status_code == 404:
        return f"Endpoint {response.url} error: not found."
    elif 404 <= response.status_code < 500:
        return f"Endpoint {response.url} error: {response.content}."
    elif response.status_code >= 500:
        return f"Endpoint {response.url} error: {response.content}."

    return False


