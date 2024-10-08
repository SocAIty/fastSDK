import json
from urllib.parse import urlparse

from fastsdk.web.req.request_handler import RequestHandler


class RequestHandlerRunpod(RequestHandler):
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

        # "status" is a refresh call so just send it
        if "/status/" in url:
            return self.httpx_client.post(url=url, headers=headers, timeout=timeout)

         # add endpoint route: fast-task-api takes the route as "path" parameter
        # Reparse method e.g. myservice/swap_img to myservice/run + post_params
        # if socaity endpoint, the method name will come as "path" parameter within the post_params
        # if method name not in url, then path is just ignored
        runpod_url = "https://api.runpod.ai/v2/"
        if runpod_url in url:
            latter_part = url[len(runpod_url):]
            pod_id, path = latter_part.split("/")
            url = f"{runpod_url}{pod_id}/run"
        else:  # localhost
            parsed_url = urlparse(url)
            path = parsed_url.path
            url = f"{parsed_url.scheme}://{parsed_url.netloc}/run"

        # get rid of the "run" prefix
        if path.startswith("run"):
            path = path[3:]

        post_params["path"] = path
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


