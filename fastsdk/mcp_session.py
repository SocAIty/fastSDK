"""Streamable HTTP session to an MCP server, shared by the definition loader and the runtime transport.

The MCP SDK reports transport failures as one generic ``MCPError`` inside nested
task-group exception groups. ``open_session`` observes the HTTP exchange itself,
so an egress rejection or an authorization challenge surfaces as a typed error.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Sequence, Tuple

import httpx2

from fastsdk.requires import requires
from fastsdk.service_specification_loader.inspect_policy import InspectRejected, check_public_url

from media_toolkit import media_from_any

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared.exceptions import MCPError
    from mcp.types import AudioContent, CallToolResult, ImageContent, InitializeResult, PaginatedRequestParams, TextContent
except ImportError:  # fastsdk[mcp] is optional; @requires guards every entry point.
    ClientSession = streamable_http_client = InitializeResult = PaginatedRequestParams = MCPError = None
    AudioContent = CallToolResult = ImageContent = TextContent = None

MCP_EXTRA = "fastsdk[mcp]"
# Guard on a module that only mcp>=2 ships: an mcp 1.x install would pass a plain "mcp" check
# while the imports above fell back to None.
MCP_MODULE = "mcp.client.client"

_RESOURCE_METADATA = re.compile(r'resource_metadata="([^"]+)"')


class MCPAuthRequired(InspectRejected):
    """The MCP server answered 401.

    ``alternatives`` names the credential kinds the one connector slot accepts:
    ``secret`` (a personal access token) always, ``oauth`` when the protected
    resource metadata lists an authorization server.
    """

    def __init__(
        self,
        url: str,
        resource_metadata: Optional[str] = None,
        authorization_servers: Sequence[str] = (),
        scopes: Sequence[str] = (),
    ):
        self.url = url
        self.resource_metadata = resource_metadata
        self.authorization_servers = list(authorization_servers)
        self.scopes = list(scopes)
        self.alternatives = ["secret", "oauth"] if self.authorization_servers else ["secret"]
        super().__init__(
            f"The MCP server at '{url}' requires authorization. Connect with an access token or OAuth.",
            "auth_required",
        )


class MCPAuthFailed(InspectRejected):
    """The ``auth`` flow itself failed: registration, the user's consent, or the token exchange."""

    def __init__(self, url: str, reason: str):
        self.url = url
        super().__init__(f"Authorizing with the MCP server at '{url}' failed. {reason}", "oauth_failed")


class MCPToolError(RuntimeError):
    """``tools/call`` answered ``isError``; the message is the tool's text content."""


class _ExchangeObserver:
    """Records what the MCP SDK folds into a generic error: egress rejections and the 401 challenge."""

    def __init__(self, url: str, public_only: bool, with_auth: bool):
        self.url = url
        self.public_only = public_only
        self.with_auth = with_auth
        self.rejected: Optional[InspectRejected] = None
        self.challenge: Optional[str] = None

    async def on_request(self, request: httpx2.Request) -> None:
        if not self.public_only:
            return
        try:
            check_public_url(str(request.url))
        except InspectRejected as exc:
            self.rejected = exc
            raise

    async def on_response(self, response: httpx2.Response) -> None:
        if response.status_code == 401:
            self.challenge = response.headers.get("www-authenticate", "")

    def translate(self, error: Exception) -> Exception:
        if self.rejected is not None:
            return self.rejected
        leaves = list(_leaves(error))
        # The auth flow raises its own exception inside the transport; protocol failures stay MCPError.
        auth_failure = next((leaf for leaf in leaves if not isinstance(leaf, MCPError)), None)
        if self.with_auth and self.challenge is not None and auth_failure is not None:
            return MCPAuthFailed(self.url, str(auth_failure))
        if self.challenge is not None:
            match = _RESOURCE_METADATA.search(self.challenge)
            return MCPAuthRequired(self.url, match.group(1) if match else None)
        return leaves[0] if len(leaves) == 1 else error


@requires(MCP_MODULE, pip_name=MCP_EXTRA)
@asynccontextmanager
async def open_session(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
    public_only: bool = False,
    max_event_bytes: Optional[int] = None,
    auth: Optional[httpx2.Auth] = None,
) -> AsyncIterator[Tuple[ClientSession, InitializeResult]]:
    """Open, initialize and finally close one MCP session.

    Args:
        url: Streamable HTTP endpoint of the server.
        headers: Sent on every request, e.g. the ``Authorization`` bearer.
        timeout: Per-request timeout in seconds.
        public_only: Run the egress policy on every request. OAuth discovery and
            token requests run through the same client, so they are checked too.
        max_event_bytes: Cap for one SSE event; None disables it.
        auth: An ``httpx2.Auth`` such as the MCP SDK's ``OAuthClientProvider``.

    Raises:
        MCPAuthRequired: The server answered 401.
        MCPAuthFailed: ``auth`` was given and its flow failed (``oauth_failed``).
        InspectRejected: ``egress_blocked`` under ``public_only``.
    """
    observer = _ExchangeObserver(url, public_only, with_auth=auth is not None)
    hooks = {"request": [observer.on_request], "response": [observer.on_response]}
    try:
        async with (
            httpx2.AsyncClient(headers=headers, timeout=timeout, event_hooks=hooks, auth=auth) as http,
            streamable_http_client(url, http_client=http, max_sse_event_size=max_event_bytes) as (read, write),
            ClientSession(read, write) as session,
        ):
            yield session, await session.initialize()
    except Exception as exc:
        translated = observer.translate(exc)
        if translated is exc:
            raise
        raise translated from exc


async def list_tools(session: ClientSession, limit: int) -> List[Dict[str, Any]]:
    """Follow ``tools/list`` cursors; stops once more than ``limit`` tools arrived so the cap check can reject."""
    tools: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        page = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
        tools.extend(tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in page.tools)
        cursor = page.next_cursor
        if not cursor or len(tools) > limit:
            return tools


async def call_tool(session: ClientSession, name: str, arguments: Dict[str, Any], timeout: float) -> Any:
    """Run one ``tools/call`` and map the result to a job output.

    ``structuredContent`` wins. Otherwise text stays text, image and audio become
    media files, and other content keeps its MCP JSON. One item is returned bare.

    Raises:
        MCPToolError: The tool reported an error, or asked for interactive input.
    """
    result = await session.call_tool(name, arguments, read_timeout_seconds=timeout)
    if not isinstance(result, CallToolResult):
        raise MCPToolError(f"MCP tool '{name}' asked for interactive input, which jobs cannot answer.")
    if result.is_error:
        message = " ".join(item.text for item in result.content if isinstance(item, TextContent))
        raise MCPToolError(message or f"MCP tool '{name}' failed.")
    if result.structured_content is not None:
        return result.structured_content
    outputs = [_content_output(item) for item in result.content]
    return outputs[0] if len(outputs) == 1 else outputs


def _content_output(item: Any) -> Any:
    if isinstance(item, TextContent):
        return item.text
    if isinstance(item, (ImageContent, AudioContent)):
        return media_from_any(f"data:{item.mime_type};base64,{item.data}")
    return item.model_dump(mode="json", by_alias=True, exclude_none=True)


def _leaves(error: BaseException) -> Iterator[BaseException]:
    nested = getattr(error, "exceptions", None)
    if not nested:
        yield error
        return
    for child in nested:
        yield from _leaves(child)
