"""
Loads Replicate models as ServiceDefinitions.

Replicate has two different invocation URL schemes:
- Official models:  POST https://api.replicate.com/v1/models/{owner}/{name}/predictions (no version needed)
- Community models: POST https://api.replicate.com/v1/predictions with the model version id in the body

This loader fetches the model's openapi schema via the `replicate` package (optional dependency)
and builds a ServiceDefinition with the correct service address for either scheme.
"""
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from media_toolkit.utils.dependency_requirements import requires

from apipod_registry.definitions.service_definitions import ServiceDefinition
from apipod_registry.parsers import parse_service_definition
from apipod_registry.parsers.service_adress_parser import create_service_address


_MODEL_REF_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_SPEC_FILE_SUFFIXES = (".json", ".yaml", ".yml")


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

    if not explicit:
        # A bare "owner/name" string could also be a relative file path.
        if ref.lower().endswith(_SPEC_FILE_SUFFIXES) or Path(ref).exists():
            return None

    return ref


@requires("replicate")
def load_replicate_service(model_ref: str, api_key: Optional[str] = None) -> ServiceDefinition:
    """
    Load a Replicate model as a ServiceDefinition by fetching its openapi schema from the Replicate API.

    Args:
        model_ref: Model reference in the form "owner/name" (see parse_replicate_model_ref).
        api_key: Replicate API key. Falls back to the REPLICATE_API_KEY environment variable.

    Returns:
        ServiceDefinition with specification="replicate" and the correct service address
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

    service_def = parse_service_definition(model.latest_version.openapi_schema)
    service_def.id = f"replicate-{model.owner}-{model.name}"
    service_def.display_name = f"{model.owner}/{model.name}"
    service_def.specification = "replicate"
    if model.description:
        service_def.description = model.description

    if _is_official_model(model, api_key):
        # Official models: version-less calls to the models endpoint.
        address = f"https://api.replicate.com/v1/models/{model.owner}/{model.name}"
    else:
        # Community models: calls go to /v1/predictions; the version id is sent in the request body.
        address = f"https://api.replicate.com/v1/predictions/{model.latest_version.id}"
    service_def.service_address = create_service_address(address, "replicate")

    return service_def


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
