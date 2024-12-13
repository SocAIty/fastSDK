from copy import copy
from typing import Union
from pydantic import BaseModel


class EndPoint:
    def __init__(
            self,
            endpoint_route: str,
            get_params: Union[dict, BaseModel] = None,
            post_params: Union[dict, BaseModel] = None,
            file_params: dict = None,
            header_params: dict = None,
            timeout: float = 3600,
            refresh_interval: float = 0.5
    ):
        """
        :param endpoint_route: for example api/img2img/stable_diffusion
        :param get_params: Defines the parameters which are send as url?params=... to the endpoint.
            It is a dict in format {param_name: param_type} for example {"my_text": str}.
        :param post_params: Defines the parameters which are send as post parameters.
            Expects a dict in format {param_name: param_type} for example {"my_text": str}
        :param file_params:
        :param timeout: time until the request fails.
        """
        # remove slash at beginning
        self.endpoint_route = endpoint_route if endpoint_route[0] != "/" else endpoint_route[1:]
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self.get_params = get_params if get_params is not None else {}
        self.post_params = post_params if post_params is not None else {}
        self.file_params = file_params if file_params is not None else {}
        self.headers = header_params if header_params is not None else {}

    def request_params_as_dict(self):
        parse = lambda x: x.dict(exclude_unset=True) if isinstance(x, BaseModel) else copy(x)
        all_params = parse(self.get_params)
        all_params.update(parse(self.post_params))
        all_params.update(parse(self.file_params))
        return all_params

        #all_params = {k: v for k, v in self.get_params.items() }
        #all_params.update(self.post_params)
        #all_params.update(self.file_params)
        #return all_params


    #@staticmethod
    #def _parse_request_params(pams, *args, **kwargs):
    #    if isinstance(pams, BaseModel):
    #        base_model_class = type(pams)
    #        get_params = base_model_class.model_validate(*args, **kwargs)
    #        return get_params.dict(exclude_unset=True)
#
    #    _named_args = {k: v for k, v in zip(pams, args)}
    #    # update with kwargs (fill values)
    #    _named_args.update(kwargs)
    #    # filter out the parameters that are not in the endpoint definition
    #    return {k: v for k, v in _named_args.items() if k in pams}
#
    #def prepare_parameters_for_request(self, *args, **kwargs):
    #    """
    #    Matches and evaluates the parameters in *args and **kwargs regarding the endpoint definition.
    #    """
    #    get_pams = self._parse_request_params(self.get_params, *args, **kwargs)
    #    post_pams = self._parse_request_params(self.post_params, *args, **kwargs)
    #    file_pams = self._parse_request_params(self.file_params, *args, **kwargs)
    #    return get_pams, post_pams, file_pams, self.headers

