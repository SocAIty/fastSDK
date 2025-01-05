import json
from fastsdk.web.req.request_handler import RequestHandler


class RequestHandlerReplicate(RequestHandler):
    """
    Works with Replicate API. https://replicate.com/docs/topics/predictions/create-a-prediction
    """
    async def request(
            self,
            url: str = None,
            get_params: dict = None,
            post_params: dict = None,
            headers: dict = None,
            files: dict = None,
            timeout: float = None
    ):
        """
          Makes a request to the given url.
          :param get_params: The parameters to be sent in the GET request.
          :param post_params: The parameters to be sent in the POST request.
          :param url: The url of the request.
          :param headers: The header_params of the request.
          :param files: The files to be sent in the request.
          :param timeout: The timeout of the request.
          :return: The response of the request.
          """
        # make dicts if they are None avoids assignment errors like headers[axyfd]
        get_params = {} if get_params is None else get_params
        post_params = {} if post_params is None else post_params
        headers = {} if headers is None else headers
        headers = self._add_authorization_to_headers(headers)

        # Strategy:
        # Official models '/models/' -> Normal post request
        # Deployment '/deployments/' -> Normal post request
        # Community models '/predictions'/ -> Add version parameter and is get request
        # Refresh call '/predictions?job_id=' -> Get request

        # Refresh call send directly. Refresh calls strictly require get requests.
        if "/predictions/" in url:
            return self.httpx_client.get(url=url, headers=headers, timeout=timeout)
        # Add version parameter for community models to make predictions
        elif "/predictions" in url and self.service_address.version is not None:
            post_params["version"] = self.service_address.version

        # every other param goes into the post_params
        if get_params is not None:
            post_params.update(get_params)

        # deal with the files
        if files is not None:
            file_size = sum([v.file_size('mb') for v in files.values()])
            if self.cloud_handler is not None and file_size > self.upload_to_cloud_handler_limit_mb:
                uploaded_files = {
                    k: self.cloud_handler.upload(v.file_name, v.file_content, folder=None)
                    for k, v in files.items()
                }
                post_params.update(uploaded_files)
            else:
                files = {k: v.to_base64() for k, v in files.items()}
                post_params.update(files)

        data = json.dumps({"input": post_params})
        return self.httpx_client.post(url=url, data=data, headers=headers, timeout=timeout)



