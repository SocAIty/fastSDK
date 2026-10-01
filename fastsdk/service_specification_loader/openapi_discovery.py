"""Discover an OpenAPI document from a URL.

Order is fixed and cheap (regex + a few GETs, no HTML parser):

1. GET the given URL. If the body is already a spec, stop.
2. Collect candidate spec URLs from the Link header (RFC 8631 / ``vnd.oai``).
3. If the body is HTML or JavaScript, regex-extract ``<link>``, Swagger UI /
   Redoc / Scalar / RapiDoc config, and a few same-origin script assets.
4. Probe conventional filenames on the URL prefix and the origin.

First body that parses as OpenAPI or Swagger wins.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from httpx import HTTPError, TimeoutException

try:
    import yaml
except ImportError:
    yaml = None  # YAML specs are skipped when PyYAML is not installed


_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_HEADERS = {
    "Accept": "application/json, application/yaml, application/vnd.oai.openapi+json, application/linkset+json, text/html;q=0.8, */*;q=0.5",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
_MAX_CANDIDATES = 28
_MAX_JS_ASSETS = 4

# Conventional spec locations (autoswagger DIRECT_SPEC_PATHS + well-known / Spring / GitLab).
SPEC_PATHS = (
    "/openapi.json",
    "/openapi.yaml",
    "/openapi.yml",
    "/swagger.json",
    "/swagger.yaml",
    "/swagger.yml",
    "/.well-known/openapi.json",
    "/.well-known/openapi.yaml",
    "/v3/api-docs",
    "/v2/api-docs",
    "/api-docs",
    "/api/openapi.json",
    "/api/swagger.json",
    "/docs/openapi.json",
    "/docs/swagger.json",
    "/redoc/openapi.json",
    "/swagger/v1/swagger.json",
    "/swagger/v3.json",
    "/swagger.v3.json",
    "/v1/openapi.json",
    "/v2/openapi.json",
    "/v3/openapi.json",
    "/v1/swagger.json",
    "/v2/swagger.json",
    "/v3/swagger.json",
    "/api/v3/openapi.json",
    "/api/v4/openapi",
    "/api/v4/openapi.json",
    "/-/openapi",
    "/openapi",
    "/swagger",
)

_SPEC_FILE = re.compile(
    r"(?:openapi|swagger)[^/\s\"']*\.(?:json|ya?ml)$|"
    r"(?:^|/)(?:openapi2?|swagger)(?:\.(?:v\d+))?\.json$|"
    r"(?:^|/)(?:v\d+/)?api-docs/?$|"
    r"(?:^|/)\.well-known/openapi",
    re.I,
)
_SPEC_HREF = re.compile(
    r"""(?:href|src|data-url|data-spec|spec-url|specurl)\s*=\s*["']([^"']+)["']""",
    re.I,
)
_UNQUOTED_HREF = re.compile(r"""href\s*=\s*(https?://[\w./:@%+-]+|/[\w./@%+-]+)""", re.I)
_LINK_TAG = re.compile(r"<link\b([^>]*)>", re.I)
_ATTR = re.compile(r"""(\w+)\s*=\s*["']([^"']+)["']""")
_JS_URL = re.compile(
    r"""url\s*:\s*["']([^"']+)["']|"""
    r"""urls\s*:\s*\[\s*\{\s*url\s*:\s*["']([^"']+)["']|"""
    r"""["']?(?:swaggerUrl|openapiUrl|specUrl|spec_url|spec-url|definitionURL|defaultDefinitionUrl|configUrl)["']?\s*[:=]\s*["']([^"']+)["']|"""
    r"""spec-url\s*=\s*["']([^"']+)["']""",
    re.I,
)
_ABS_SPEC = re.compile(
    r"""https?://[^\s"'<>]+(?:openapi|swagger|api-docs|api-specification|api-registry)[^\s"'<>]*""",
    re.I,
)
_SCRIPT_SRC = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.I)
_JS_ASSET = re.compile(
    r"swagger-initializer|swagger-config|swagger-ui|redoc|rapidoc|scalar|swashbuckle",
    re.I,
)
_SKIP_ASSET = re.compile(r"\.(?:css|png|jpe?g|gif|svg|woff2?|ttf|map)(?:\?|$)", re.I)
_LINK_PART = re.compile(r'<([^>]+)>\s*;?\s*(.*)')
_LINK_PARAM = re.compile(r"""(\w+)\s*=\s*["']?([^"',;]+)["']?""")


class OpenAPIDiscoveryError(ValueError):
    """No OpenAPI document was found. ``probed`` is ``(url, result)`` for each GET."""

    def __init__(self, url: str, probed: List[tuple], truncated: bool = False):
        self.url = url
        self.probed = list(probed)
        self.truncated = truncated
        super().__init__(format_discovery_failure(url, self.probed, truncated))


def format_discovery_failure(url: str, probed: List[tuple], truncated: bool = False) -> str:
    """User-facing hint: what was fetched, and that a direct spec URL is the next step."""
    lines = [
        f"Could not discover an OpenAPI document at {url}.",
        "Paste a direct openapi.json or openapi.yaml URL.",
    ]
    if probed:
        lines.append(f"Probed {len(probed)} URLs:")
        lines.extend(f"- {item}: {reason}" for item, reason in probed)
    else:
        lines.append("No URL was fetched.")
    if truncated:
        lines.append(
            f"Stopped after {_MAX_CANDIDATES} probes. Further candidates were not fetched."
        )
    return "\n".join(lines)


def load_openapi_from_url(url: str, timeout: float = 45.0) -> Tuple[str, Dict[str, Any]]:
    """Fetch an OpenAPI document, discovering it when ``url`` is a docs page or API root.

    Returns:
        ``(spec_url, spec)``. ``spec_url`` is the final URL the document was served from, the canonical
        address of that API regardless of which docs page or root the caller pasted.
    """
    timeout_cfg = httpx.Timeout(timeout, connect=min(5.0, timeout))
    notes: List[tuple] = []
    flags = {"truncated": False}
    with httpx.Client(timeout=timeout_cfg, follow_redirects=True, headers=_HEADERS) as client:
        found = _discover(client, url, notes, flags)
    if found:
        return found
    raise OpenAPIDiscoveryError(url, notes, truncated=flags["truncated"])


def _discover(
    client: httpx.Client, url: str, notes: List[tuple], flags: Dict[str, bool],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    tried: Set[str] = set()
    first = _get(client, url, tried, notes)
    if first is not None:
        found = _spec_or_note(first, url, notes)
        if found:
            return found
        pending = _candidates_from_response(first)
        pending.extend(_script_assets(first))
    else:
        pending = []

    queue = _unique(pending)
    resolved = str(first.url) if first is not None else url
    js_left = _MAX_JS_ASSETS
    conventional_added = False
    index = 0
    while index < len(queue) or not conventional_added:
        if index >= len(queue) and not conventional_added:
            for extra in _conventional_urls(url, resolved):
                if extra not in tried and extra not in queue:
                    queue.append(extra)
            conventional_added = True
            continue
        if len(tried) >= _MAX_CANDIDATES:
            flags["truncated"] = True
            break
        candidate = queue[index]
        index += 1
        response = _get(client, candidate, tried, notes)
        if response is None:
            continue
        found = _spec_or_note(response, candidate, notes)
        if found:
            return found
        extras = _candidates_from_response(response)
        extras.extend(_json_siblings(candidate))
        if js_left and _is_javascript(response):
            js_left -= 1
            extras.extend(_spec_urls_in_text(response.text, str(response.url)))
        insert_at = index
        for extra in _prefer_spec_files(extras):
            if extra not in tried and extra not in queue:
                queue.insert(insert_at, extra)
                insert_at += 1
    return None


def _get(
    client: httpx.Client, url: str, tried: Set[str], notes: List[tuple],
) -> Optional[httpx.Response]:
    absolute = url.split("#", 1)[0].rstrip()
    if not absolute or absolute in tried:
        return None
    tried.add(absolute)
    try:
        return client.get(absolute)
    except TimeoutException:
        notes.append((absolute, "timed out"))
    except HTTPError as exc:
        notes.append((absolute, f"request failed ({type(exc).__name__})"))
    return None


def _spec_or_note(
    response: httpx.Response, requested: str, notes: List[tuple],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Return ``(final_url, spec)``, or record why this response is not an OpenAPI document."""
    final = str(response.url).split("#", 1)[0]
    spec, reason = _read_spec(response)
    if spec is not None:
        return final, spec
    if final.rstrip("/") != requested.split("#", 1)[0].rstrip("/"):
        reason = f"{reason} (redirected to {final})"
    notes.append((requested, reason))
    return None


def _read_spec(response: httpx.Response) -> Tuple[Optional[Dict[str, Any]], str]:
    """Parsed OpenAPI or Swagger document, or ``None`` and the reason the body is not one."""
    status = response.status_code
    if status >= 400:
        return None, f"HTTP {status}"
    data = _parse_payload(response.text or "", (response.headers.get("content-type") or "").lower())
    if not isinstance(data, dict):
        return None, f"HTTP {status}, body is not a JSON or YAML object"
    if "openapi" not in data and "swagger" not in data:
        return None, f"HTTP {status}, no openapi or swagger field"
    if "paths" not in data and "webhooks" not in data:
        return None, f"HTTP {status}, missing paths"
    return data, ""


def _parse_payload(text: str, content_type: str) -> Any:
    stripped = text.lstrip()
    if "json" in content_type or stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    if yaml is not None and (
        "yaml" in content_type or stripped.startswith("openapi:") or stripped.startswith("swagger:")
    ):
        try:
            return yaml.safe_load(text)
        except Exception:
            return None
    return None


def _candidates_from_response(response: httpx.Response) -> List[str]:
    base = str(response.url)
    found: List[str] = []
    found.extend(spec_urls_from_link_header(response.headers.get("link"), base))
    found.extend(_service_desc_from_linkset(response))
    if _looks_markup(response) or _is_javascript(response):
        found.extend(_spec_urls_in_text(response.text, base))
    return [_deref_repo_url(item) for item in found]


def spec_urls_from_link_header(header: Optional[str], base: str) -> List[str]:
    """RFC 8288 Link values whose rel or type points at an OpenAPI document."""
    if not header:
        return []
    urls: List[str] = []
    for raw in header.split(","):
        match = _LINK_PART.search(raw)
        if not match:
            continue
        target, params = match.group(1).strip(), match.group(2).lower()
        rel = type_ = ""
        for key, value in _LINK_PARAM.findall(params):
            if key == "rel":
                rel = value
            elif key == "type":
                type_ = value
        if (
            rel in {"service-desc", "describedby", "api-catalog"}
            or "vnd.oai" in type_
            or "openapi" in type_
        ):
            urls.append(urljoin(base, target))
    return urls


def _spec_urls_in_text(text: str, base: str) -> List[str]:
    urls: List[str] = []
    for tag in _LINK_TAG.findall(text):
        attrs = {key.lower(): value for key, value in _ATTR.findall(tag)}
        rel = attrs.get("rel", "").lower()
        type_ = attrs.get("type", "").lower()
        href = attrs.get("href")
        if href and (
            rel in {"service-desc", "describedby"}
            or "vnd.oai" in type_
            or "openapi" in type_
        ):
            urls.append(urljoin(base, href))
    for match in _SPEC_HREF.finditer(text):
        urls.append(urljoin(base, match.group(1)))
    for match in _UNQUOTED_HREF.finditer(text):
        urls.append(urljoin(base, match.group(1)))
    for match in _JS_URL.finditer(text):
        value = next((group for group in match.groups() if group), None)
        if value:
            urls.append(urljoin(base, value))
    urls.extend(_ABS_SPEC.findall(text))
    return [item for item in _unique(urls) if _looks_spec_url(item)]


def _service_desc_from_linkset(response: httpx.Response) -> List[str]:
    """RFC 9727 API catalog: ``service-desc`` hrefs inside a linkset document."""
    ctype = (response.headers.get("content-type") or "").lower()
    data = _parse_payload(response.text or "", ctype)
    if not isinstance(data, dict):
        return []
    hrefs: List[str] = []
    for item in data.get("linkset") or []:
        if not isinstance(item, dict):
            continue
        for desc in item.get("service-desc") or []:
            href = desc.get("href") if isinstance(desc, dict) else None
            if href:
                hrefs.append(href)
    return hrefs


def _deref_repo_url(url: str) -> str:
    """GitHub / GitLab blob pages are HTML. The raw file is the spec."""
    if "/-/blob/" in url:
        return url.replace("/-/blob/", "/-/raw/")
    parsed = urlparse(url)
    if parsed.netloc != "github.com":
        return url
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, ref = parts[0], parts[1], parts[3]
        rest = "/".join(parts[4:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{rest}"
    return url


def _json_siblings(url: str) -> List[str]:
    """YAML specs need PyYAML. Also try the .json sibling that many hosts publish."""
    parsed = urlparse(url)
    path = parsed.path or ""
    if not path.endswith((".yaml", ".yml")):
        return []
    json_path = re.sub(r"\.ya?ml$", ".json", path, flags=re.I)
    return [parsed._replace(path=json_path).geturl()]


def _script_assets(response: httpx.Response) -> List[str]:
    if not _looks_markup(response):
        return []
    base = str(response.url)
    origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    assets: List[str] = []
    for src in _SCRIPT_SRC.findall(response.text):
        absolute = urljoin(base, src)
        if _SKIP_ASSET.search(absolute) or not _JS_ASSET.search(absolute):
            continue
        if urlparse(absolute).netloc != urlparse(origin).netloc:
            continue
        assets.append(absolute)
        if len(assets) >= _MAX_JS_ASSETS:
            break
    return assets


def _conventional_urls(original: str, resolved: str) -> List[str]:
    urls: List[str] = []
    for base in _probe_bases(original, resolved):
        for path in SPEC_PATHS:
            urls.append(urljoin(f"{base}/", path.lstrip("/")))
    return urls


def _probe_bases(original: str, resolved: str) -> List[str]:
    bases: List[str] = []
    for raw in (resolved, original):
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            continue
        origin = f"{parsed.scheme}://{parsed.netloc}"
        prefix = f"{origin}{parsed.path}".rstrip("/")
        if prefix and not _SPEC_FILE.search(parsed.path or ""):
            bases.append(prefix)
        bases.append(origin)
    return _unique(bases)


def _looks_spec_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if _SKIP_ASSET.search(path):
        return False
    name = path.rsplit("/", 1)[-1] if path else ""
    if _SPEC_FILE.search(path) or _SPEC_FILE.search(name):
        return True
    haystack = f"{name}?{parsed.query}".lower()
    return any(
        token in haystack
        for token in (
            "openapi",
            "swagger",
            "api-docs",
            "api-specification",
            "api-registry",
            "vnd.oai",
        )
    )


def _looks_markup(response: httpx.Response) -> bool:
    ctype = (response.headers.get("content-type") or "").lower()
    if "html" in ctype or "xml" in ctype:
        return True
    text = (response.text or "").lstrip()
    return text.startswith("<!") or text.startswith("<html") or text.startswith("<HTML")


def _is_javascript(response: httpx.Response) -> bool:
    ctype = (response.headers.get("content-type") or "").lower()
    if "javascript" in ctype or "ecmascript" in ctype:
        return True
    path = urlparse(str(response.url)).path.lower()
    return path.endswith(".js")


def _prefer_spec_files(urls: Iterable[str]) -> List[str]:
    """Try filenames that are already documents before HTML hops."""
    items = _unique(urls)
    files = [url for url in items if _SPEC_FILE.search(urlparse(url).path or "")]
    hops = [url for url in items if url not in files]
    return files + hops


def _unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered
