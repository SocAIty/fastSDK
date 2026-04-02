from typing import Optional, Union
import json
import httpx

from fastsdk.service_interaction.response.api_job_status import APIJobStatus
from fastsdk.service_interaction.response.base_response import BaseJobResponse, RunpodJobResponse, SocaityJobResponse, ReplicateJobResponse
from fastsdk.service_interaction.response.response_parser_strategies import SocaityResponseParser, RunpodResponseParser, ReplicateResponseParser


class ResponseParser:
    def __init__(self):
        self.strategies = [
            SocaityResponseParser(),
            ReplicateResponseParser(),
            RunpodResponseParser(),
        ]

    async def parse_response(self, response: httpx.Response, parse_media: bool = True) -> Union[BaseJobResponse, bytes, None, dict]:
        """Parse HTTP response into appropriate response object."""
        if not response:
            return None

        content_type = response.headers.get("Content-Type", "")
        
        # Handle Server-Sent Events (Streaming)
        # The response body is NOT consumed here — it stays open so
        # the caller can iterate over chunks via response.aiter_text().
        if "text/event-stream" in content_type:
            return SocaityJobResponse(id="stream", status=APIJobStatus.STREAMING)

        # Ensure content is read if it was a streaming response
        try:
            if not response.is_closed:
                await response.aread()
        except httpx.ResponseNotRead:
            await response.aread()
        except Exception:
            pass

        if "application/json" not in content_type:
            return response.content

        try:
            data = response.json()

            for strategy in self.strategies:
                if strategy.can_parse(data):
                    parsed_response = strategy.parse(data, parse_media=parse_media)

                    if isinstance(parsed_response, RunpodJobResponse) and isinstance(parsed_response.result, str):
                        try:
                            nested_data = json.loads(parsed_response.result)
                            if any(s.can_parse(nested_data) for s in self.strategies):
                                nested_response = await self.parse_response(httpx.Response(200, json=nested_data))
                                parsed_response.update(nested_response)
                        except json.JSONDecodeError:
                            pass

                    return parsed_response

            return data

        except json.JSONDecodeError:
            return response.content

    async def parse_media_result(self, parsed_response: BaseJobResponse) -> BaseJobResponse:
        """Parse media from a previously parsed response (that had parse_media=False)."""
        if not isinstance(parsed_response, BaseJobResponse):
            return None

        if isinstance(parsed_response, SocaityJobResponse):
            parsed_response.result = SocaityResponseParser._parse_media_result(parsed_response.result)

        if isinstance(parsed_response, ReplicateJobResponse):
            parsed_response.result = ReplicateResponseParser()._parse_media_result(parsed_response.result)
        
        return parsed_response

    @staticmethod
    async def check_response_status(response: httpx.Response) -> Optional[str]:
        """Check HTTP response status code and return error message if applicable.

        Because the HTTP client may use ``stream=True``, the response body
        is not necessarily loaded yet.  We ``await response.aread()`` before
        accessing ``.content`` so that ``ResponseNotRead`` is never raised.
        """
        if 200 <= response.status_code < 300:
            return None

        error_messages = {
            401: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            403: f"Endpoint {response.url} error: Unauthorized. Did you forget to set the API key?",
            404: f"Endpoint {response.url} error: not found. Check the URL and API key.",
        }

        if response.status_code in error_messages:
            return error_messages[response.status_code]
        elif response.status_code >= 400:
            # Ensure the body is loaded before accessing .content
            try:
                await response.aread()
            except Exception:
                pass
            return f"Endpoint {response.url} error: {response.content}."

        return None
