from copy import copy
from typing import Union
from pydantic import BaseModel


class EndPoint:
    """
    Defines with which parameters a request to an endpoint can be made.
    """
    def __init__(
            self,
            endpoint_route: str,
            query_params: Union[dict, BaseModel] = None,
            body_params: Union[dict, BaseModel] = None,
            file_params: dict = None,
            header_params: dict = None,
            timeout: float = 3600,
            refresh_interval: float = 0.5
    ):
        """
        :param endpoint_route: for example api/img2img/stable_diffusion
        :param query_params: Defines the parameters which are send as url?params=... to the endpoint.
            It is a dict in format {param_name: param_type} for example {"my_text": str}.
        :param body_params: Defines the parameters which are send in the request body e.g. post.
            Expects a dict in format {param_name: param_type} for example {"my_text": str}
        :param file_params: Defines the parameters which are send as files. Might be, read, converted, uploaded.
        :param header_params: Additional headers to be sent with the request.
        :param timeout: time in seconds until the request to the endpoint fails.
        :param refresh_interval: in which interval in seconds is the status checkpoint called.
        """
        self.endpoint_route = endpoint_route.strip("/")  # remove slash at beginning and end
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self.query_params = query_params if query_params is not None else {}
        self.body_params = body_params if body_params is not None else {}
        self.file_params = file_params if file_params is not None else {}
        self.headers = header_params if header_params is not None else {}

    def get_parameter_definition_as_dict(self):
        parse = lambda x: x.dict(exclude_unset=True) if isinstance(x, BaseModel) else copy(x)
        all_params = parse(self.query_params)
        all_params.update(parse(self.body_params))
        all_params.update(parse(self.file_params))
        return all_params

