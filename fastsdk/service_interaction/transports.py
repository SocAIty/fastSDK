"""Invocation transports: how one prepared job reaches its provider.

``JobTasks`` owns the shared pipeline (files, polling, streaming, results) and
delegates the protocol-specific prepare and send steps to the stack's transport.
Transports are stateless; they read the client, file handler and parser from
``job.provider_stack``, so a swapped file handler applies immediately.

Both transports apply auth at send time from the job's own ``credentials``,
so concurrent jobs on one shared stack never see each other's secrets.
"""
import logging
from typing import Any

from apipod_registry.parsers.mcp_parser import MCP_ARGUMENTS_PARAM
from media_toolkit import MediaDict
from socaity_schemas.public.providers import StreamingResponse
from socaity_schemas.public.spec.address import service_url

from fastsdk.mcp_session import call_tool, open_session
from fastsdk.service_interaction.api_seex import APISeex
from fastsdk.service_interaction.request import RequestData

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 60.0


def _timeout_s(job: APISeex) -> float:
    timeout_hint = getattr(job.endpoint, "timeout_hint_s", None)
    return float(timeout_hint) if timeout_hint else _DEFAULT_TIMEOUT_S


class HttpTransport:
    """HTTP: ``APIClient`` builds and sends the request, ``ResponseParser`` reads the answer."""

    async def prepare(self, job: APISeex) -> RequestData:
        return job.provider_stack.api_client.format_request_params(job.endpoint, job.input)

    async def send(self, job: APISeex, request_data: RequestData) -> Any:
        stack = job.provider_stack
        stack.api_client.apply_auth(request_data.headers, request_data.query_params, job.endpoint, job.credentials)

        if isinstance(request_data.file_params, MediaDict) and request_data.file_params:
            if request_data.body_content_type == stack.api_client._JSON_BODY_CONTENT_TYPE:
                for name, value in request_data.file_params.items():
                    request_data.body_params[name] = stack.api_client._serialize_json_body_file_value(value)
                request_data.file_params = {}
            else:
                non_file_params = request_data.file_params.get_non_file_params(include_urls=True)
                if non_file_params:
                    request_data.body_params.update(non_file_params)

                file_model_fields, raw_files = stack.api_client.partition_media_for_multipart(
                    job.endpoint, request_data.file_params
                )
                if file_model_fields:
                    request_data.body_params.update(file_model_fields)
                request_data.file_params = raw_files
                request_data.file_params = await stack.file_handler.prepare_files_for_send(
                    request_data.file_params
                )
        elif request_data.file_params:
            request_data.file_params = await stack.file_handler.prepare_files_for_send(request_data.file_params)

        logger.info("send_request | Sending request to %s", request_data.url)
        response = await stack.api_client.send_request(request_data, timeout_s=_timeout_s(job))
        logger.info(
            "send_request | Received response: status=%d content_type=%s",
            response.status_code, response.headers.get("Content-Type"),
        )

        error = await stack.parser.check_response_status(response)
        if error:
            logger.error("send_request | Request failed: %s", error)
            raise Exception(error)

        parsed = await stack.parser.parse_response(response, materialize_media=job.materialize_media)

        if isinstance(parsed, StreamingResponse):
            logger.info("send_request | Detected direct stream response")
            job.direct_response = response
            job.runtime.refresh_stream_state()
        else:
            if not response.is_closed:
                await response.aclose()

        logger.info("send_request | Parsed response type: %s", type(parsed).__name__)
        return parsed


class MCPTransport:
    """MCP: one Streamable HTTP session per call, ``tools/call`` with the ``arguments`` object.

    The session opens, initializes, calls and closes inside ``send``; there is
    no session pool. Tool errors raise, so the job ends ``FAILED``.
    """

    async def prepare(self, job: APISeex) -> RequestData:
        api_client = job.provider_stack.api_client
        arguments = (job.input or {}).get(MCP_ARGUMENTS_PARAM) or {}
        return RequestData(body_params=arguments, url=service_url(api_client.address))

    async def send(self, job: APISeex, request_data: RequestData) -> Any:
        headers = job.provider_stack.api_client.apply_auth(
            request_data.headers, endpoint=job.endpoint, credentials=job.credentials,
        )
        timeout_s = _timeout_s(job)
        logger.info("send_request | Calling MCP tool %s at %s", job.endpoint.operation_id, request_data.url)
        async with open_session(request_data.url, headers, timeout_s) as (session, _):
            return await call_tool(session, job.endpoint.operation_id, request_data.body_params, timeout_s)
