import json
from urllib.parse import urlparse

import httpx

from fastsdk.web.req.request_handler import RequestHandler
from fastsdk.web.req.s3_bucket import S3Bucket
from media_toolkit import media_from_any
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.jobs.async_jobs.async_job import AsyncJob
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.definitions.enums import EndpointSpecification


class RequestHandlerRunpod(RequestHandler):

    @staticmethod
    def add_get_params_to_url(url: str, get_params: dict):
        """
        Adds the get parameters to the url.
        :param url: The url to add the parameters to.
        :param get_params: The parameters to add.
        :return: The url with the parameters added.
        """
        if get_params:
            url += "?"
            for k, v in get_params.items():
                url += f"{k}={v}&"
            url = url[:-1]
        return url

    async def request(
            self,
            url: str, get_params: dict, post_params: dict, headers: dict, files: dict, timeout: float
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

        # add endpoint route: fast-task-api takes the route as "path" parameter
        runpod_url = "https://api.runpod.ai/v2/"
        if runpod_url in url:
            latter_part = url[len(runpod_url):]
            pod_id, path = latter_part.split("/")[0]
            url = f"{runpod_url}/{pod_id}/run"
        else:
            parsed_url = urlparse(url)
            path = parsed_url.path
            url = f"{parsed_url.scheme}://{parsed_url.netloc}/run"
        if path.startswith("run"):
            path = path[3:]
        post_params["path"] = path
        # every other param goes into the post_params
        post_params.update(get_params)


        # deal with the files
        if self.s3_bucket is not None:
            bucket_name = None
            uploaded_files = {
                k: self.s3_bucket.upload_in_memory_object(v.file_name, v.file_content, bucket_name=bucket_name)
                for k, v in files.items()
            }
            post_params.update(uploaded_files)
        else:
            files = {k: v.to_base64() for k, v in files.items()}
            post_params.update(files)

        data = json.dumps({"input": post_params})
        return self.httpx_client.post(url=url, data=data)  # , files=files, headers=headers, timeout=timeout)



