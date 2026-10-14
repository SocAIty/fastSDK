"""Inspect limits and the outbound egress policy for remote specification sources.

Limits bound what one inspect may cost: a document over ``MAX_DOCUMENT_BYTES``
or a contract over ``MAX_OPERATIONS`` is rejected before anything is persisted.

The egress policy protects servers that inspect user-supplied URLs. It runs
before every request and redirect and checks the DNS-resolved addresses, so a
public name pointing at a private address is rejected too. Local SDK use leaves
it off; ``inspect_service(public_only=True)`` turns it on.
"""
import socket
from ipaddress import IPv6Address, ip_address
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx2

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
MAX_OPERATIONS = 500
MAX_CONCURRENT_PROBES = 4

ProgressCallback = Callable[[str, str], None]
"""``(stage, message)``. Stages: ``discover``, ``fetch``, ``parse``."""

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_METADATA_HOSTS = frozenset({"metadata", "metadata.google.internal", "metadata.goog"})


class InspectRejected(ValueError):
    """The source broke an inspect limit or the egress policy. ``code`` names the rule."""

    def __init__(self, message: str, code: str):
        self.code = code
        super().__init__(message)


def report(on_progress: Optional[ProgressCallback], stage: str, message: str) -> None:
    if on_progress is not None:
        on_progress(stage, message)


def check_public_url(url: str) -> None:
    """Reject non-http(s) schemes and hosts that resolve to non-public addresses.

    Loopback, private, link-local (which covers the 169.254.169.254 metadata
    address), shared, reserved, multicast and unspecified addresses all fail.
    Every resolved address must be public, not just the first.

    Raises:
        InspectRejected: ``egress_blocked`` with the offending host or scheme.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise InspectRejected(f"Only http and https URLs can be inspected, got '{parsed.scheme}'.", "egress_blocked")
    host = (parsed.hostname or "").lower()
    if not host or host in _METADATA_HOSTS:
        raise InspectRejected(f"Host '{host}' is not reachable from Socaity.", "egress_blocked")
    try:
        resolved = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise InspectRejected(f"Host '{host}' does not resolve.", "egress_blocked") from exc
    for *_, sockaddr in resolved:
        address = ip_address(str(sockaddr[0]).split("%", 1)[0])
        if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast:
            raise InspectRejected(
                f"Host '{host}' resolves to a non-public address ({address}). Socaity only inspects public APIs.",
                "egress_blocked",
            )


def egress_hooks(public_only: bool) -> dict:
    """httpx2 ``event_hooks`` that run the egress policy on every request, redirects included."""
    if not public_only:
        return {}
    return {"request": [lambda request: check_public_url(str(request.url))]}


def read_limited(client: httpx2.Client, url: str) -> httpx2.Response:
    """GET ``url`` and buffer the body, aborting once it exceeds ``MAX_DOCUMENT_BYTES``.

    Raises:
        InspectRejected: ``document_too_large``.
        httpx2.HTTPError: Transport failures, unchanged.
    """
    with client.stream("GET", url) as response:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_DOCUMENT_BYTES:
            raise _too_large(url)
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_DOCUMENT_BYTES:
                raise _too_large(url)
    # The body is already decoded; a kept content-encoding would decode it twice.
    headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in ("content-encoding", "content-length")]
    return httpx2.Response(response.status_code, headers=headers, content=bytes(body), request=response.request)


def check_operation_count(count: int, source: str) -> None:
    if count > MAX_OPERATIONS:
        raise InspectRejected(
            f"'{source}' declares {count} operations; inspect accepts at most {MAX_OPERATIONS}. "
            "Use a smaller document or a subset of the API.",
            "too_many_operations",
        )


def _too_large(url: str) -> InspectRejected:
    limit_mb = MAX_DOCUMENT_BYTES // (1024 * 1024)
    return InspectRejected(
        f"The document at '{url}' is larger than {limit_mb} MB. Use a smaller document or a subset of the API.",
        "document_too_large",
    )
