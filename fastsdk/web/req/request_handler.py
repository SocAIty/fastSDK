from typing import Union, Tuple

import httpx
from pydantic import BaseModel

from fastCloud import FastCloud
from fastCloud.core import BaseUploadAPI
from fastsdk.jobs.async_jobs.async_job import AsyncJob
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.service_adress import ServiceAddress, create_service_address
from media_toolkit import MediaFile


class RequestHandler:
    def __init__(
            self,
            service_address: Union[str, ServiceAddress],
            async_job_manager: AsyncJobManager = None,
            api_key: str = None,
            fast_cloud: FastCloud = None,
            upload_to_cloud_threshold_mb: int = 5,
            max_upload_file_size_mb: int = 1000,
            *args, **kwargs
    ):
        """
        :param service_address: The service_address or URL of the service.
        :param async_job_manager: The async_jobs job manager to use.
        :param fast_cloud:
            If given: files are uploaded to the cloud provider
                (azure, s3, replicate, socaity..) and the file is sent as uploaded_file_url to the endpoint
            If None: send files as bytes or base64 to the endpoint.
        :param upload_to_cloud_threshold_mb:
            If the combined file size is greater than this limit, the file is uploaded to the cloud handler.
        :param max_upload_file_size_mb: an upper limit for the upload. If > this limit the job will return immediately.
        """
        if not isinstance(service_address, ServiceAddress):
            service_address = create_service_address(service_address)

        self.service_address = service_address
        self.api_key = api_key

        # self.service_spec = determine_service_type(self.service_address)
        # add the async_jobs job manager or create a new one
        self.async_job_manager = async_job_manager if async_job_manager is not None else AsyncJobManager()
        self.httpx_client = httpx.AsyncClient()

        self.fast_cloud = fast_cloud
        self.upload_to_cloud_threshold_mb = upload_to_cloud_threshold_mb
        self.max_upload_file_size_mb = max_upload_file_size_mb
        self._attached_files_format = 'httpx'
        self._attach_files_to = 'body'

    def set_cloud_storage(self, cloud_storage: FastCloud, upload_to_cloud_threshold: int = 10):
        self.fast_cloud = cloud_storage
        self.upload_to_cloud_threshold_mb = upload_to_cloud_threshold

    @staticmethod
    def _format_params(p_def: Union[BaseModel, dict], *args, **kwargs) -> dict:
        """
        Restructures the request parameters to be a well formed dict matching the definition in p_def.
        Allows the request to be called arbitrary like request_endpoint(def, whatever1, whatever2, my_param1='value') ..
        Therefore it feeds the values of args and kwargs into the dict.
        If p_def is a BaseModel; the model_fields are filled and the model is validated.
        In all other cases the dict is just created with all values given.
        :param p_def:
            The definition of the parameters. As dict {param_name: param_type} or as a pydantic model.
        :param args: arbitrary values that are matched with the p_def
        :param kwargs: arbitrary values that are matched with the p_def
        """
        if p_def is None:
            return {}

        if isinstance(p_def, BaseModel):
            base_model_class = type(p_def)
            # match *args with model_fields
            _named_args = {k: v for k, v in zip(base_model_class.model_fields.keys(), args)}
            _named_args.update(kwargs)
            # validate the model_hosting_info with the given args and kwargs
            get_params = base_model_class.model_validate(_named_args)
            # return as dict
            return get_params.dict(exclude_unset=True)

        _named_args = {k: v for k, v in zip(p_def, args)}
        # update with kwargs (fill values)
        _named_args.update(kwargs)
        # filter out the parameters that are not in the endpoint definition
        return {k: v for k, v in _named_args.items() if k in p_def}

    def _add_authorization_to_headers(self, headers: dict = None):
        headers = {} if headers is None else headers
        if self.api_key is not None:
            headers["Authorization"] = "Bearer " + self.api_key
        if len(headers) == 0:
            headers = None
        return headers

    async def _format_request_params(self, endpoint: EndPoint, *args, **kwargs) -> Tuple[dict, dict, dict, dict]:
        """
        Formats the request parameters to match the given endpoint definition.
        after parameters will have structure { 'param_name': 'param_value' } for query, body, files, headers
        files are not yet read or uploaded.
        :param endpoint: The endpoint definition
        :param args: arbitrary values that are matched with the endpoint def
        :param kwargs: arbitrary values that are matched with the endpoint def
        """
        # Format the parameters
        query_p = self._format_params(endpoint.query_params, *args, **kwargs)
        body_p = self._format_params(endpoint.body_params, *args, **kwargs)
        file_p = self._format_params(endpoint.file_params, *args, **kwargs)
        headers = self._add_authorization_to_headers(endpoint.headers)
        return query_p, body_p, file_p, headers

    @staticmethod
    async def _read_files(files: dict) -> dict:
        """
        Reads the files to be uploaded into memory.
        :returns dict in form { 'file_name': MediaFile }
        """
        # ToDo: Make an async version of MediaFile loading to be true async and to load multiple files much faster.
        return {
            k: MediaFile().from_any(v)
            for k, v in files.items()
        }

    def _convert_files_to_attachable_format(self, files: dict) -> dict:
        if self._attached_files_format == 'httpx':  # default for fasttaskapi
            return {k: v.to_httpx_send_able_tuple() for k, v in files.items()}
        elif self._attached_files_format == 'base64':  # used for example in replicate
            return {k: v.to_base64() for k, v in files.items()}
        return files

    def _upload_attach_files_to_request_params(self, body_params: dict, files: dict) -> Tuple[dict, dict]:
        """
        Attaches the files to the request parameters.
        Files get attached to body if self._attach_files_to == 'body'. Else they are attached as files.

        :param body_params: The body parameters of the request
        :param files: The files to attach.
        :return: The body_params, files
        """
        files = self._convert_files_to_attachable_format(files)
        if self._attach_files_to == 'body':
            body_params.update(files)
            files = {}

        return body_params, files

    async def _upload_files(self, body_params: dict, files: dict) -> Tuple:
        """
        Uploads the files based on different upload strategies:
        (1) If the cloud handler is not set:
            - If self._attach_files_to == 'body' the files are attached to the body_params.
            - else the files are attached as files in httpx.
        (2) If the cloud handler is set:
            - If the combined file size is below the limit, the files are attached using method (1)
            - If the combined file size is above the limit, the files are uploaded using the cloud handler.

        :param files: The files to be uploaded.
        :returns:
            - None, None: If no files were uploaded.
            - dict, None: If files were uploaded. The dict is formatted as { file_name: download_url }.
            - None, dict: If files were not uploaded. The dict contains the files in a format that can be sent with httpx.
        """
        if files is None or len(files) == 0:
            return files

        if self.fast_cloud is None:
            return self._upload_attach_files_to_request_params(body_params=body_params, files=files)

        # determine combined file size
        file_size = sum([v.file_size('mb') for v in files.values()])
        # Case 1: Attach directly if size is below limit
        if file_size < self.upload_to_cloud_threshold_mb:
            return self._upload_attach_files_to_request_params(body_params, files)
        elif self.max_upload_file_size_mb is not None and file_size > self.max_upload_file_size_mb:
            raise Exception(f"The file you have provided exceed the max upload limit of {self.max_upload_file_size_mb}mb")
        else:
            # upload async
            if isinstance(self.fast_cloud, BaseUploadAPI):
                uploaded_files = {k: self.fast_cloud.upload_async(v) for k, v in files.items()}
                # await all uploads
                for k, v in uploaded_files.items():
                    uploaded_files[k] = await v
            else:
                uploaded_files = {k: self.fast_cloud.upload(v) for k, v in files.items()}

            body_params = {} if body_params is None else body_params
            body_params.update(uploaded_files)
            return body_params, {}

    async def _process_file_params(self, body_params: dict, file_params: dict) -> Tuple[dict, dict]:
        """
        Converts the file params to a format that can be sent with httpx.
        if the total file size > 10 and cloud handler is given, upload the files to the cloud handler
        - if files were uploaded, the file content is replaced with the file url
        - if files are not uploaded, they are converted to a with httpx send able format.
          In the latter case they are also attached to body_params because they are not treated explicitly by httpx.
        :param file_params: The file params to convert.
        :param body_params: The body_params to attach read files to.
        :return: converted file params, body_params with the files attached.
        """
        if not file_params or len(file_params) == 0:
            return file_params, body_params

        file_params = await self._read_files(file_params)
        body_params, file_params = await self._upload_files(body_params=body_params, files=file_params)
        return body_params, file_params

    @staticmethod
    def _add_query_params_to_url(url: str, query_parameters: dict):
        """
        Adds the get parameters to the url.
        :param url: The url to add the parameters to.
        :param query_parameters: The parameters to add.
        :return: The url with the parameters added.
        """
        if query_parameters:
            url += "?"
            for k, v in query_parameters.items():
                url += f"{k}={str(v)}&"
            url = url[:-1]
        return url

    def _prepare_request_url(self, endpoint: EndPoint, query_params: dict = None) -> str:
        url = f"{self.service_address.url}/{endpoint.endpoint_route}"
        url = self._add_query_params_to_url(url, query_parameters=query_params)
        return url

    async def _prepare_request(self, endpoint: EndPoint, *args, **kwargs):
        query_p, body_p, file_p, headers = await self._format_request_params(endpoint, *args, **kwargs)
        body_p, file_p = await self._process_file_params(body_p, file_p)

        # add query parameters to the url like '/endpoint?param1=value1&param2=value2'
        url = self._prepare_request_url(endpoint, query_params=query_p)
        return url, query_p, body_p, file_p, headers

    async def _request_endpoint(self, endpoint: EndPoint, timeout: float = None, *args, **kwargs):
        # Format, read files, upload files, format urls
        url, query_params, body_params, file_p, headers = await self._prepare_request(endpoint, *args, **kwargs)
        return await self.httpx_client.post(url=url, params=body_params, files=file_p, headers=headers, timeout=timeout)

    def request_endpoint(self, endpoint: EndPoint, callback: callable = None, *args, **kwargs) -> AsyncJob:
        """
        Makes a request to the given endpoint with the parameters given in args and kwargs.
        :param endpoint: The endpoint definition.
        :param callback: The callback function to call when the request is done.
        :param args: arbitrary values that are matched with the endpoint def
        :param kwargs: arbitrary values that are matched with the endpoint def
        :return: An AsyncJob object that can be used to get the result of the request.
        """
        req_coroutine = self._request_endpoint(endpoint, *args, timeout=endpoint.timeout, **kwargs)
        async_job = self.async_job_manager.submit(req_coroutine, callback=callback, delay=None)
        return async_job

    def request_url(
            self,
            url: str,
            method: str = "GET",
            files: dict = None,
            callback: callable = None,
            delay: float = None,
            timeout: float = None,
        ) -> AsyncJob:
        """
        Makes a request to the given url.
        Adds the authorization header if an api key is configured for the request handler.
        :param url: The url to make the get request to. Can be a relative path.
        :param method: The method of the request. GET or POST.
        :param files: The files to send with the request formatted as httpx_send_able_tuple.
        :param callback: The callback function to call when the request is done.
        :param delay: The delay in seconds before the request is sent.
        :param timeout: The timeout in seconds of the request.

        :return: An AsyncJob object that can be used to get the result of the request.
        """
        # for relative paths
        if "http" not in url:
            url = url.lstrip("/")  # remove leading slash
            url = f"{self.service_address.url}/{url}"

        headers = self._add_authorization_to_headers()

        if method.upper() == "GET":
            req_coroutine = self.httpx_client.get(url=url, headers=headers, timeout=timeout)
        elif method.upper() == "POST":
            req_coroutine = self.httpx_client.post(url=url, files=files, headers=headers, timeout=timeout)
        elif method.upper() == "PUT":
            req_coroutine = self.httpx_client.put(url=url, files=files, headers=headers, timeout=timeout)
        elif method.upper() == "DELETE":
            req_coroutine = self.httpx_client.delete(url=url, headers=headers, timeout=timeout)
        else:
            req_coroutine = self.httpx_client.post(url=url, headers=headers, timeout=timeout)

        return self.async_job_manager.submit(req_coroutine, callback=callback, delay=delay)
