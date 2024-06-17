from typing import Union
import httpx

from socaity_client.web.definitions.socaity_server_response import SocaityServerResponse, SocaityServerJobStatus


def is_socaity_server_response(json: dict) -> bool:
    if not "endpoint_protocol" in json or json["endpoint_protocol"] != "socaity":
        return False

    required_fields = ["id", "status"]
    return all(field in json for field in required_fields)


def parse_response(response: httpx.Response) -> Union[SocaityServerResponse, bytes, dict, object]:
    """
    Parses the response of a request.
    :param response: The response of the request either formatted as json or the raw _content_buffer
    :return: The parsed response as SocaityServerResponse or the raw _content_buffer.
    """
    if response is None:
        return None

    if response.headers.get("Content-Type") == "application/json":
        result = response.json()
        #message = parse_status_code(response)

        if is_socaity_server_response(result):
            result['status'] = SocaityServerJobStatus(result['status'])
            result = SocaityServerResponse(**result)

        return result
    else:
        return response.content


def has_request_status_code_error(response: httpx.Response) -> Union[str, bool]:
    """
    Parses the status code of a response.
    :param response: The response of the request.
    :return: an error message if there was an error, otherwise False.
    """
    if response.status_code == 200:
        return False
    elif response.status_code == 404:
        return f"Endpoint {response.url} error: not found."
    elif 404 <= response.status_code < 500:
        return f"Endpoint {response.url} error: {response.content}."
    elif response.status_code >= 500:
        return f"Endpoint {response.url} error: {response.content}."

    return False


