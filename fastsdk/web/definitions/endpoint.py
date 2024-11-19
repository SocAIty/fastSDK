
class EndPoint:
    def __init__(
            self,
            endpoint_route: str,
            get_params: dict = None,
            post_params: dict = None,
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

    def params(self):
        all_params = {k: v for k,v in self.get_params.items() }
        all_params.update(self.post_params)
        all_params.update(self.file_params)
        return all_params


