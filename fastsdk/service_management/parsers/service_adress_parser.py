from typing import Union
from urllib.parse import urlparse
from fastsdk.service_management.service_definition import ServiceSpecification, ServiceAddress, RunpodServiceAddress, ReplicateServiceAddress, SocaityServiceAddress


def _url_sanitize(url: str):
    """
    Add http:// if not present and remove trailing slash
    """
    if not url:
        return url

    url = url.strip("/")  # remove prefix and suffix slashes

    # looks like something else!
    if "/" not in url and "www." not in url and "http" not in url:
        return url

    if not url.startswith("http") and not url.startswith("https"):
        url = f"http://{url}"
    return url


def parse_runpod_url(url: str) -> tuple:
    """
    Parses the runpod url to get the base runpod url, pod_id (and path).
    Accepted formats:
    - https://api.runpod.ai/v2/pod_id/run
    - https://api.runpod.ai/v2/pod_id/path  - path is the route in fast-task-api.
    - pod_id/run
    - pod_id
    - localhost:port/pod_id/run
    """
    runpod_url = "https://api.runpod.ai/v2/"

    # if the url is not a full url, assume that it is a pod_id
    if 'http' not in url:
        if "localhost" in url:
            # case localhost:port/pod_id/run
            url = f"http://{url}"
        else:
            # case pod_id, pod_id/run
            url = f"{runpod_url}{url}"

    parsed_url = urlparse(url)

    # remove v2 and run
    path = parsed_url.path
    if path.startswith("/v2/"):
        path = path[4:]

    path = path.replace("/run", "")

    pod_id = None
    if "api.runpod.ai" in url:
        # get pod_id from path
        parts = path.split("/", 1)
        pod_id = parts[0]
        if len(parts) > 1:
            path = "/".join(parts[1:])
        else:
            path = ""

        url = f"{parsed_url.scheme}://{parsed_url.netloc}/v2/{pod_id}"
    else:
        url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    return url, pod_id, path


def parse_replicate_url(url: str):
    """
    Parses the replicate url to get the model name and version.
    Accepted formats
    - user/modelname
    - user/modelname:versionnumber
    - https://api.replicate.com/v1/models/user/modelname
    - https://api.replicate.com/v1/models/user/modelname:versionnumber
    - https://api.replicate.com/v1/predictions/versionnumber
    - version number like 847dfa8b01e739637fc76f480ede0c1d76408e1d694b830b5dfb8e547bf98405

    :param url: The replicate url
    :return: Tuple of address, model_name, model_version.
        e.g. ("https://api.replicate.com/v1/models/user/modelname", "user/modelname", "versionnumber")
        or ("https://api.replicate.com/v1/predictions/", None, "versionnumber")
    """
    base_url = "https://api.replicate.com/v1"
    models_url = f"{base_url}/models"
    predictions_url = f"{base_url}/predictions"

    # cases
    #  https://api.replicate.com/v1/models/user/modelname
    #  https://api.replicate.com/v1/models/user/modelname:versionnumber
    if url.startswith(models_url):
        parts = url[len(models_url) + 1:].split("/")
        if len(parts) < 2:
            raise Exception(f"Couldn't parse replicate url {url}")

        usr, model_name = parts[0], parts[1]
        version = None
        if ":" in model_name:
            model_name, version = model_name.split(":")

        parsed_uri = f"{models_url}/{usr}/{model_name}"
        parsed_uri = f"{parsed_uri}:{version}" if version else parsed_uri
        parsed_uri = f"{parsed_uri}/predictions"
        return parsed_uri, f"{usr}/{model_name}", version

    # case https://api.replicate.com/v1/predictions/versionnumber
    elif url.startswith(predictions_url):
        version = url.split("/")[-1]
        return predictions_url, None, version
    # case user/modelname
    elif "/" in url:
        return base_url + url, url, None
    else:
        return predictions_url, None, url


def determine_service_type(service_url: str) -> ServiceSpecification:
    if "socaity.ai" in service_url:
        return "socaity"

    if "api.runpod.ai" in service_url:
        return "runpod"

    if "api.replicate.com" in service_url:
        return "replicate"

    return "other"


def create_service_address(address: Union[str, dict, ServiceAddress], provider: str = None) -> Union[ServiceAddress, ReplicateServiceAddress, RunpodServiceAddress, SocaityServiceAddress]:
    """
    Creates the appropriate service address object based on the address provided.
    Returns instances of the BaseModel classes from service_definition module.
    :param address: The address to create the service address from. The type of the service address (provider) will be determined by the structure of the service address.property
    :param provider: Optional provider to guide the service manager additionally in resolving service adresses. Can be 'replicate', 'runpod' or 'socaity'.
    """
    if not address:
        return None
        
    if isinstance(address, ServiceAddress):
        return address

    if isinstance(address, dict):
        adr = address.get("address", None)
        version = address.get("version", None)
        model_name = address.get("model_name", None)

        if version or model_name:
            # Create ReplicateServiceAddress from service_definition
            url, parsed_model_name, parsed_version = parse_replicate_url(model_name or version or adr)
            return ReplicateServiceAddress(
                url=_url_sanitize(url),
                model_name=model_name or parsed_model_name,
                version=version or parsed_version
            )

        return create_service_address(adr)

    if isinstance(address, str):
        st = provider or determine_service_type(address)
        if st == "socaity":
            # Create SocaityServiceAddress from service_definition
            return SocaityServiceAddress(url=_url_sanitize(address))
        if st == "replicate":
            # Create ReplicateServiceAddress from service_definition
            url, model_name, version = parse_replicate_url(address)
            return ReplicateServiceAddress(
                url=_url_sanitize(url),
                model_name=model_name,
                version=version
            )
        elif st == "runpod":
            # Create RunpodServiceAddress from service_definition
            url, pod_id, path = parse_runpod_url(address)
            return RunpodServiceAddress(
                url=_url_sanitize(url),
                pod_id=pod_id,
                path=path
            )

    # Create generic ServiceAddress from service_definition
    return ServiceAddress(url=_url_sanitize(address) if isinstance(address, str) else address)
