from typing import Optional, Union
import json
import httpx


from fastsdk.definitions.base_response import BaseJobResponse, RunpodJobResponse
from fastsdk.client.definitions.server_response.response_parser_strategies import SocaityResponseParser, \
    RunpodResponseParser, ReplicateResponseParser, ResponseParserStrategy


class ResponseParser:
    def __init__(self):
        self.strategies: list[ResponseParserStrategy] = [
            SocaityResponseParser(),
            RunpodResponseParser(),
            ReplicateResponseParser()
        ]

    def parse_response(self, response: httpx.Response) -> Union[BaseJobResponse, bytes, dict, None]:
        """Parse HTTP response into appropriate response object."""
        if not response:
            return None

        if "application/json" not in response.headers.get("Content-Type", ""):
            return response.content

        try:
            data = response.json()

            # Try each parser strategy
            for strategy in self.strategies:
                if strategy.can_parse(data):
                    parsed_response = strategy.parse(data)

                    # Handle nested Runpod output
                    if isinstance(parsed_response, RunpodJobResponse) and isinstance(parsed_response.result, str):
                        try:
                            nested_data = json.loads(parsed_response.result)
                            if any(strategy.can_parse(nested_data) for strategy in self.strategies):
                                nested_response = self.parse_response(httpx.Response(200, json=nested_data))
                                parsed_response.update(nested_response)
                        except json.JSONDecodeError:
                            pass

                    return parsed_response

            return data  # Return raw JSON if no parser matches

        except json.JSONDecodeError:
            return response.content

    @staticmethod
    def check_response_status(response: httpx.Response) -> Optional[str]:
        """Check HTTP response status code and return error message if applicable."""
        if response.status_code == 200:
            return None

        error_messages = {
            401: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            403: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            404: f"Endpoint {response.url} error: not found. Check the URL and API key.",
        }

        if response.status_code in error_messages:
            return error_messages[response.status_code]
        elif response.status_code >= 400:
            return f"Endpoint {response.url} error: {response.content}."

        return None
