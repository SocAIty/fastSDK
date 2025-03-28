from typing import Union
from urllib.parse import urlparse

from fastsdk.definitions.enums import EndpointSpecification


class ServiceAddress:
    def __init__(self, address: Union[str, dict]):
        """
        :param address: The address of the service. An url or a dictionary with the key "url"
        """
        if isinstance(address, str):
            self.url = self._url_sanitize(address)
        elif isinstance(address, dict) and "url" in address:
            self.url = self._url_sanitize(address["url"])

    @staticmethod
    def _url_sanitize(url: str):
        """
        Add http: // if not present and remove trailing slash
        """
        url = url.strip("/")  # remove prefix and suffix slashes
        if not url.startswith("http") and not url.startswith("https"):
            url = f"http://{url}"
        return url

    def __str__(self):
        return self.url


class RunpodServiceAddress(ServiceAddress):
    def __init__(self, address: str):
        self.url, self.pod_id, _ = self.parse_url(address)
        super().__init__(self.url)

    @staticmethod
    def parse_url(url: str) -> tuple:
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


class SocaityServiceAddress(ServiceAddress):
    def __init__(self, address: str):
        super().__init__(address)


class ReplicateServiceAddress(ServiceAddress):
    def __init__(self, address: str | None = None, model_name: str | None = None, version: str | None = None):
        if address:
            self.url, self.model_name, self.version = self.parse_url(address)
        elif not address and model_name:
            self.url, self.model_name, self.version = self.parse_url(model_name)
        elif not address and not model_name and version:
            self.url, self.model_name, self.version = self.parse_url(version)

        if not self.url and not self.model_name and not self.version:
            raise ValueError("couldn't parse replicate address. Check inputs")

        super().__init__(self.url)

    @staticmethod
    def parse_url(url: str):
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
            parts = url[len(models_url)+1:].split("/")
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


def determine_service_type(service_url: str) -> EndpointSpecification:
    if "socaity.ai" in service_url:
        return EndpointSpecification.SOCAITY

    if "api.runpod.ai" in service_url:
        return EndpointSpecification.RUNPOD

    if "api.replicate.com" in service_url:
        return EndpointSpecification.REPLICATE

    return EndpointSpecification.OTHER


def create_service_address(address: Union[str, dict, ServiceAddress]) -> Union[ServiceAddress, ReplicateServiceAddress]:
    if isinstance(address, ServiceAddress):
        return address

    if isinstance(address, dict):
        adr = address.get("address", None)
        version = address.get("version", None)
        model_name = address.get("model_name", None)

        if version or model_name:
            return ReplicateServiceAddress(address=adr, version=version, model_name=model_name)

        return create_service_address(adr)

    if isinstance(address, str):
        st = determine_service_type(address)
        if st == EndpointSpecification.SOCAITY:
            return SocaityServiceAddress(address=address)
        if st == EndpointSpecification.REPLICATE:
            return ReplicateServiceAddress(address=address)
        elif st == EndpointSpecification.RUNPOD:
            return RunpodServiceAddress(address=address)

    return ServiceAddress(address)
