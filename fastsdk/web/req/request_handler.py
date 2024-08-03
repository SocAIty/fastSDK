import json
from urllib.parse import urlparse

import httpx

from fastsdk.web.req.s3_bucket import S3Bucket
from media_toolkit import media_from_any
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.jobs.async_jobs.async_job import AsyncJob
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.definitions.enums import EndpointSpecification


class RequestHandler:
    """
    The request handler is an interface between async jobs and web req.
    1. Requests to endpoints are implemented as coroutines.
    2. It submits those request coroutines to the AsyncJobManager; where they are executed asynchronously.
    It also implements the logic to prepare the parameters for the request.
    """
    def __init__(self, service_url: str, async_job_manager: AsyncJobManager = None, s3_bucket: S3Bucket = None):
        """
        :param service_url: The url of the service.
        :param async_job_manager: The async_jobs job manager to use.
        :param s3_bucket:
            If None: send files as bytes to the endpoint.
            If given: files are uploaded to the s3 bucket and the file url is sent to the endpoint
        """
        self.service_url = service_url
        self.service_spec = self.determine_service_type(self.service_url)
        # add the async_jobs job manager or create a new one
        self.async_job_manager = async_job_manager if async_job_manager is not None else AsyncJobManager()
        self.httpx_client = httpx.Client()
        self.s3_bucket = s3_bucket


    def request_endpoint_async(self, endpoint: EndPoint, callback: callable = None, *args, **kwargs) -> AsyncJob:
        """
        Makes a request to an endpoint.
        :param endpoint: The endpoint to make the request to.
        :param callback: The callback function to call when the request is done.
        :param args: The arguments to pass to the request.
        :param kwargs: The keyword arguments to pass to the request.
        :return: The response of the request.
        """
        get_p, post_p, file_p, header_p = self._prepare_endpoint_params_for_request(endpoint, *args, **kwargs)

        return self.request_url_async(
            url=f"{self.service_url}/{endpoint.endpoint_route}",
            get_params=get_p,
            post_params=post_p,
            files=file_p,
            headers=header_p,
            callback=callback
        )

    def request_url_async(
            self,
            url: str,
            get_params: dict = None,
            post_params: dict = None,
            headers: dict = None,
            files: dict = None,
            callback: callable = None,
            delay: float = None,
            timeout: float = None
    ) -> AsyncJob:
        """
        Makes a request to the given url.
        :param url: The url of the request.
        :param get_params: The parameters to be sent in the GET request.
        :param post_params: The parameters to be sent in the POST request.
        :param headers: The header_params of the request.
        :param files: The files to be sent in the request.
        :param callback: The callback function to call when the request is done.
        :param delay: The delay in seconds before the request is made.
        :param timeout: The timeout of the request.
        :return: The response of the request as an async_jobs job.
        """
        req_coroutine = self.request(url, get_params, post_params, headers, files, timeout=timeout)

        async_job = self.async_job_manager.submit(req_coroutine, callback=callback, delay=delay)
        return async_job

    @staticmethod
    def _prepare_endpoint_params_for_request(endpoint: EndPoint, *args, **kwargs):
        # make dict from args and kwargs
        # get named args of endpoint and fill with args
        _named_args = {k: v for k, v in zip(endpoint.params(), args)}
        # update with kwargs
        _named_args.update(kwargs)

        # sort the parameters by paramater typ
        get_params = {k: v for k, v in _named_args.items() if k in endpoint.get_params}
        post_params = {k: v for k, v in _named_args.items() if k in endpoint.post_params}
        file_params = {k: v for k, v in _named_args.items() if k in endpoint.file_params}
        header_params = {k: v for k, v in _named_args.items() if k in endpoint.headers}

        # convert files to send able format
        file_params = {
            k: media_from_any(v, endpoint.file_params.get(k, None))
            for k, v in file_params.items()
        }

        return get_params, post_params, file_params, header_params

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
        if self.service_spec == EndpointSpecification.RUNPOD:
            return await self.request_runpod(url, get_params, post_params, headers, files, timeout)

        url = RequestHandler.add_get_params_to_url(url, get_params)

        # deal with the files
        if self.s3_bucket is not None:
            bucket_name = None
            uploaded_files = {
                k: self.s3_bucket.upload_in_memory_object(v.file_name, v.file_content, bucket_name=bucket_name)
                for k, v in files.items()
            }
            post_params.update(uploaded_files)
            files = None
        else:
            files = {k: v.to_httpx_send_able_tuple() for k, v in files.items()}


        return self.httpx_client.post(url=url, params=post_params, files=files, headers=headers, timeout=timeout)

        # Todo: Find out why async httpx is so much slower than requests at the moment
        #async with httpx.AsyncClient() as client:
        #    return await client.post(url, params=post_params, files=read_files, headers=headers, timeout=timeout)


