"""
Loads Replicate models as AIServices.

Replicate has two different invocation URL schemes:
- Official models:  POST https://api.replicate.com/v1/models/{owner}/{name}/predictions (no version needed)
- Community models: POST https://api.replicate.com/v1/predictions with the model version id in the body

This loader fetches the model's openapi schema via the `replicate` package (optional dependency)
and builds an AIService with the correct service address for either scheme.
"""
import os
import re
from typing import Optional

import httpx
from media_toolkit.utils.dependency_requirements import requires

from apipod_registry import create_service, materialize_contract
from socaity_schemas.platform import AIService


_MODEL_REF_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def parse_replicate_model_ref(source) -> Optional[str]:
    """
    Detect whether a spec source refers to a Replicate model and return its "owner/name" reference.

    Accepted forms:
    - "replicate:owner/name"
    - "https://replicate.com/owner/name"
    - "https://api.replicate.com/v1/models/owner/name[/predictions]"
    - "owner/name" (only if it doesn't point to a local spec file)

    Returns:
        The "owner/name" model reference, or None if the source is not a Replicate model reference.
    """
    if not isinstance(source, str):
        return None

    ref = source.strip()
    explicit = False

    if ref.startswith("replicate:"):
        ref = ref[len("replicate:"):].strip("/")
        explicit = True
    elif ref.startswith(("http://", "https://")):
        host_and_path = ref.split("://", 1)[1]
        for prefix in ("replicate.com/", "www.replicate.com/", "api.replicate.com/v1/models/"):
            if host_and_path.startswith(prefix):
                ref = host_and_path[len(prefix):].strip("/")
                explicit = True
                break
        if not explicit:
            return None

    if ref.endswith("/predictions"):
        ref = ref[: -len("/predictions")]
    ref = ref.split(":", 1)[0]  # drop a version tag like owner/name:version

    if not _MODEL_REF_PATTERN.match(ref):
        return None

    return ref


@requires("replicate")
def load_replicate_service(model_ref: str, api_key: Optional[str] = None) -> AIService:
    """
    Load a Replicate model as an AIService by fetching its openapi schema from the Replicate API.

    Args:
        model_ref: Model reference in the form "owner/name" (see parse_replicate_model_ref).
        api_key: Replicate API key. Falls back to the REPLICATE_API_KEY environment variable.

    Returns:
        AIService with a provider="replicate" deployment and the correct service address
        for official ("models" scheme) or community ("predictions" scheme) models.
    """
    import replicate

    api_key = api_key or os.getenv("REPLICATE_API_KEY")
    if not api_key:
        raise ValueError(
            f"A Replicate API key is required to load '{model_ref}'. "
            "Set the REPLICATE_API_KEY environment variable or pass api_key."
        )

    client = replicate.Client(api_token=api_key)
    model = client.models.get(model_ref)
    if model.latest_version is None:
        raise ValueError(f"Replicate model '{model_ref}' has no published version; cannot load its openapi schema.")

    # materialize_contract with provider="replicate" marks the contract job-based
    # (Replicate wraps every model in its predictions job API).
    contract = materialize_contract(model.latest_version.openapi_schema, provider="replicate")

    if _is_official_model(model, api_key):
        # Official models: version-less calls to the models endpoint.
        address = f"https://api.replicate.com/v1/models/{model.owner}/{model.name}"
    else:
        # Community models: calls go to /v1/predictions; the version id is sent in the request body.
        address = f"https://api.replicate.com/v1/predictions/{model.latest_version.id}"

    service = create_service(
        contract,
        address=address,
        provider="replicate",
        service_id=f"replicate-{model.owner}-{model.name}",
        name=f"{model.owner}/{model.name}",
    )
    service.display_name = f"{model.owner}/{model.name}"
    if model.description:
        service.description = model.description

    return service


def _is_official_model(model, api_key: str) -> bool:
    is_official = getattr(model, "is_official", None)
    if is_official is None:
        # Older versions of the replicate package don't expose the field -> ask the REST API directly.
        try:
            response = httpx.get(
                f"https://api.replicate.com/v1/models/{model.owner}/{model.name}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
            response.raise_for_status()
            is_official = response.json().get("is_official", False)
        except httpx.HTTPError:
            is_official = False
    return bool(is_official)
