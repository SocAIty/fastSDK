"""MCP definition loader: ``initialize`` plus paginated ``tools/list`` into the registry's MCP document.

The document is what ``apipod_registry``'s ``MCPParser`` reads::

    {"mcp": <initialize result>, "tools": [<tools/list entries>], "security_schemes": {...}}

A server that answers 401 raises ``MCPAuthRequired`` enriched with its RFC 9728
protected-resource metadata, so callers can offer a token or OAuth for the one slot.
"""
import asyncio
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx2

from fastsdk.mcp_session import MCP_EXTRA, MCP_MODULE, MCPAuthRequired, list_tools, open_session
from fastsdk.requires import requires
from fastsdk.service_specification_loader.inspect_policy import (
    MAX_DOCUMENT_BYTES,
    MAX_OPERATIONS,
    ProgressCallback,
    check_public_url,
    report,
)

SECURITY_SCHEME = "bearer"
"""The one credential slot of an MCP connector. A token and OAuth both end up as this bearer."""


def is_mcp_url(url: str) -> bool:
    """``mcp://``, an ``mcp`` host label (``mcp.stripe.com``, ``drivemcp.googleapis.com``) or an ``mcp`` path segment."""
    parsed = urlparse(url.strip().lower())
    if parsed.scheme == "mcp":
        return True
    if parsed.scheme not in ("http", "https"):
        return False
    first_label = (parsed.hostname or "").split(".", 1)[0]
    return "mcp" in first_label or any("mcp" in segment for segment in parsed.path.split("/"))


def mcp_endpoint(url: str) -> str:
    """The Streamable HTTP URL: ``mcp://host/path`` means ``https://host/path``."""
    url = url.strip()
    return "https://" + url[len("mcp://"):] if url.lower().startswith("mcp://") else url


@requires(MCP_MODULE, pip_name=MCP_EXTRA)
def load_mcp_from_url(
    url: str,
    api_key: Optional[str] = None,
    timeout: float = 30.0,
    public_only: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    auth: Optional[httpx2.Auth] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Read the tool definitions of an MCP server.

    Args:
        url: Streamable HTTP endpoint; ``mcp://host/path`` means ``https://host/path``.
        api_key: Bearer token for servers that require authorization.
        timeout: Per-request timeout in seconds.
        public_only: Run the egress policy on every request.
        on_progress: Receives ``discover`` and ``fetch`` stages.
        auth: ``httpx2.Auth`` for the session, e.g. an ``OAuthClientProvider`` whose
            redirect and callback hooks the caller supplies.

    Returns:
        ``(endpoint_url, document)``.

    Raises:
        MCPAuthRequired: The server needs a credential and none (or a rejected one) was sent.
        InspectRejected: Egress policy or an SSE event above the document size limit.
    """
    endpoint = mcp_endpoint(url)
    report(on_progress, "discover", f"Connecting to the MCP server at {endpoint}")
    document = asyncio.run(_load(endpoint, api_key, timeout, public_only, auth))
    report(on_progress, "fetch", f"Listed {len(document['tools'])} tools from {endpoint}")
    return endpoint, document


async def _load(
    url: str, api_key: Optional[str], timeout: float, public_only: bool, auth: Optional[httpx2.Auth],
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    try:
        async with open_session(
            url, headers, timeout, public_only, MAX_DOCUMENT_BYTES, auth,
        ) as (session, initialized):
            tools = await list_tools(session, MAX_OPERATIONS)
    except MCPAuthRequired as exc:
        raise await _with_resource_metadata(exc, timeout, public_only) from exc
    secured = api_key is not None or auth is not None
    return {
        "mcp": initialized.model_dump(mode="json", by_alias=True, exclude_none=True),
        "tools": tools,
        "security_schemes": {SECURITY_SCHEME: {"type": "http", "scheme": "bearer"}} if secured else {},
    }


async def _with_resource_metadata(error: MCPAuthRequired, timeout: float, public_only: bool) -> MCPAuthRequired:
    """RFC 9728 lookup: the challenge's ``resource_metadata`` URL, else the well-known paths. Redirects are not followed."""
    parsed = urlparse(error.url)
    well_known = f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource"
    candidates = [error.resource_metadata] if error.resource_metadata else [
        well_known + parsed.path.rstrip("/"),
        well_known,
    ]
    async with httpx2.AsyncClient(timeout=timeout) as client:
        for candidate in candidates:
            if public_only:
                check_public_url(candidate)
            try:
                response = await client.get(candidate)
                metadata = response.json() if response.is_success else None
            except (httpx2.HTTPError, ValueError):
                continue
            if isinstance(metadata, dict):
                return MCPAuthRequired(
                    error.url, candidate, metadata.get("authorization_servers") or [], metadata.get("scopes_supported") or [],
                )
    return error
