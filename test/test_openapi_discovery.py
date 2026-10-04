"""OpenAPI discovery: unit checks for extractors, optional live crawl of public docs."""
import importlib.util
from pathlib import Path

_DISCOVERY = Path(__file__).resolve().parents[1] / "fastsdk" / "service_specification_loader" / "openapi_discovery.py"
_SPEC = importlib.util.spec_from_file_location("openapi_discovery", _DISCOVERY)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

load_openapi_from_url = _MOD.load_openapi_from_url
spec_urls_from_link_header = _MOD.spec_urls_from_link_header
_spec_urls_in_text = _MOD._spec_urls_in_text


def test_link_header_vnd_oai():
    urls = spec_urls_from_link_header(
        '<https://api.example.com/openapi.json>; rel="service-desc"; '
        'type="application/vnd.oai.openapi+json"',
        "https://api.example.com/",
    )
    assert urls == ["https://api.example.com/openapi.json"]


def test_link_header_describedby():
    urls = spec_urls_from_link_header(
        '</docs/swagger.json>; rel=describedby',
        "https://api.example.com/v1",
    )
    assert urls == ["https://api.example.com/docs/swagger.json"]


def test_html_link_service_desc():
    html = '<link rel="service-desc" type="application/vnd.oai.openapi+json" href="/openapi.json">'
    urls = _spec_urls_in_text(html, "https://api.example.com/")
    assert "https://api.example.com/openapi.json" in urls


def test_html_swagger_ui_and_redoc():
    html = """
    <script>
      SwaggerUIBundle({ url: "/swagger/v1/swagger.json" });
    </script>
    <redoc spec-url="https://cdn.example.com/openapi.yaml"></redoc>
    """
    urls = _spec_urls_in_text(html, "https://docs.example.com/api/")
    assert "https://docs.example.com/swagger/v1/swagger.json" in urls
    assert "https://cdn.example.com/openapi.yaml" in urls


def test_html_skips_stylesheets():
    html = '<link rel="stylesheet" href="/swagger-ui.css">'
    assert _spec_urls_in_text(html, "https://api.example.com/") == []


def test_html_swagger_url_json_key():
    html = '{"swaggerUrl":"/cloud/jira/platform/swagger-v3.v3.json"}'
    urls = _spec_urls_in_text(html, "https://developer.atlassian.com/")
    assert "https://developer.atlassian.com/cloud/jira/platform/swagger-v3.v3.json" in urls


def test_html_unquoted_openapi_href():
    html = '<a href=/api/openapi/>OpenAPI</a>'
    urls = _spec_urls_in_text(html, "https://docs.gitlab.com/api/rest/")
    assert "https://docs.gitlab.com/api/openapi/" in urls


LIVE_CASES = [
    ("Notion", "https://developers.notion.com", True),
    ("Jira Cloud", "https://developer.atlassian.com/cloud/jira/platform/rest/v3/", True),
    ("Confluence", "https://developer.atlassian.com/cloud/confluence/rest/v2/", True),
    ("Slack", "https://api.slack.com/web", False),
    ("GitHub", "https://docs.github.com/en/rest", True),
    ("Stripe", "https://docs.stripe.com/api", False),
    ("Twilio", "https://www.twilio.com/docs/usage/api", False),
    ("HubSpot", "https://developers.hubspot.com/docs/api/overview", True),
    ("Asana", "https://developers.asana.com/reference", True),
    ("Trello", "https://developer.atlassian.com/cloud/trello/rest/", True),
    ("Airtable", "https://airtable.com/developers/web/api/introduction", False),
    ("Discord", "https://discord.com/developers/docs/intro", False),
    ("OpenAI", "https://platform.openai.com/docs/api-reference", False),
    ("Mailchimp", "https://mailchimp.com/developer/marketing/api/", True),
    ("Zendesk", "https://developer.zendesk.com/api-reference/", True),
    ("Intercom", "https://developers.intercom.com/docs/references/introduction/", True),
    ("DigitalOcean", "https://docs.digitalocean.com/reference/api/", True),
    ("Cloudflare", "https://developers.cloudflare.com/api/", True),
    ("GitLab", "https://docs.gitlab.com/ee/api/rest/", True),
    ("Linear", "https://developers.linear.app/docs", False),
    ("CarbonIntensity", "https://api.carbonintensity.org.uk", True),
]


def _live_discover(url: str):
    try:
        _spec_url, spec = load_openapi_from_url(url)
    except Exception:
        return None
    title = (spec.get("info") or {}).get("title")
    version = spec.get("openapi") or spec.get("swagger")
    return version, title, len(spec.get("paths") or {})


if __name__ == "__main__":
    print(f"{'#':<3} {'App':<16} {'found':<6} {'ver':<8} {'paths':<6} title")
    for index, (name, url, _expect) in enumerate(LIVE_CASES, 1):
        result = _live_discover(url)
        if result is None:
            print(f"{index:<3} {name:<16} no")
            continue
        version, title, path_count = result
        print(f"{index:<3} {name:<16} yes    {str(version):<8} {path_count:<6} {title}")
