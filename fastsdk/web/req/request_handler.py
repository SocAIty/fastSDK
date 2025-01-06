from typing import Union, Tuple

import httpx
from pydantic import BaseModel

from fastCloud import CloudStorage
from fastsdk.jobs.async_jobs.async_job import AsyncJob
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.service_adress import ServiceAddress, create_service_address


class RequestHandler:
    def __init__(
            self,
            service_address: Union[str, ServiceAddress],
            async_job_manager: AsyncJobManager = None,
            api_key: str = None,
            cloud_handler: CloudStorage = None,
            upload_to_cloud_storage_threshold_mb: int = 10,
            *args, **kwargs
    ):
        """
        :param service_address: The service_address or URL of the service.
        :param async_job_manager: The async_jobs job manager to use.
        :param cloud_handler:
            If given: files are uploaded to the cloud provider (azure, sr) and the file url is sent to the endpoint
            If None: send files as bytes to the endpoint.
        :param upload_to_cloud_storage_threshold_mb:
            If the combined file size is greater than this limit, the file is uploaded to the cloud handler.
        """
        if not isinstance(service_address, ServiceAddress):
            service_address = create_service_address(service_address)

        self.service_address = service_address

        self.api_key = api_key
        # self.service_spec = determine_service_type(self.service_address)
        # add the async_jobs job manager or create a new one
        self.async_job_manager = async_job_manager if async_job_manager is not None else AsyncJobManager()
        self.httpx_client = httpx.AsyncClient()
        self.cloud_handler = cloud_handler
        self.upload_to_cloud_handler_limit_mb = upload_to_cloud_storage_threshold_mb
        self._non_upload_files_request_format = 'httpx'

    def set_cloud_storage(self, cloud_storage: CloudStorage, upload_to_cloud_threshold: int = 10):
        self.cloud_handler = cloud_storage
        self.upload_to_cloud_handler_limit_mb = upload_to_cloud_threshold

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
        after parameters will have structure { 'param_name': 'param_value' } for get, post, files, headers
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
        return {}

    async def _upload_files(self, files: dict) -> Tuple:
        """
        Uploads the files to the cloud handler if the total size is greater than the limit.
        :param files: The files to be uploaded.
        :returns:
            - None, None: If no files were uploaded.
            - dict, None: If files were uploaded. The dict is formatted as { file_name: download_url }.
            - None, dict: If files were not uploaded. The dict contains the files in a format that can be sent with httpx.
        """
        if files is not None:
            # determine combined file size
            file_size = sum([v.file_size('mb') for v in files.values()])

            # Todo: If it is a socaity endpoint, get the upload key from endpoint and create new cloud handler.
            # Todo: With this workaround, we can make sure, that users upload files directly to the cloud.
            if self.cloud_handler is not None and file_size > self.upload_to_cloud_handler_limit_mb:
                uploaded_files = {
                    k: self.cloud_handler.upload(v.file_name, v.file_content, folder=None)
                    for k, v in files.items()
                }
                return uploaded_files, None
            else:
                if self._non_upload_files_request_format == 'httpx':  # default for fasttaskapi
                    files = {k: v.to_httpx_send_able_tuple() for k, v in files.items()}
                elif self._non_upload_files_request_format == 'base64':  # used for example in replicate
                    files = {k: v.to_base64() for k, v in files.items()}
                return None, files

        return None, None

    async def _process_file_params(self, file_params: dict, post_params: dict) -> Tuple[dict, dict]:
        """
        Converts the file params to a format that can be sent with httpx.
        if the total file size > 10 and cloud handler is given, upload the files to the cloud handler
        - if files were uploaded, the file content is replaced with the file url
        - if files are not uploaded, they are converted to a with httpx send able format.
          In the latter case they are also attached to body_params because they are not treated explicitly by httpx.
        :param file_params: The file params to convert.
        :param post_params: The post params to attach read files to.
        :return: converted file params, post params with the files attached.
        """
        if not file_params or len(file_params) == 0:
            return file_params, post_params

        file_params = await self._read_files(file_params)
        uploaded_files, formatted_files = await self._upload_files(file_params)
        post_params.update(uploaded_files)
        file_params = formatted_files
        return file_params, post_params

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
                url += f"{k}={v}&"
            url = url[:-1]
        return url

    async def _prepare_request(self, endpoint: EndPoint, *args, **kwargs):
        get_p, post_p, file_p, headers = await self._format_request_params(endpoint, *args, **kwargs)
        file_p, post_p = await self._process_file_params(file_p, post_p)

        # add get parameters to the url
        url = self._add_query_params_to_url(self.service_address.url, get_p)

        return url, post_p, file_p, headers

    async def _request_endpoint(self, endpoint: EndPoint, timeout: float = None, *args, **kwargs):
        # Format, read files, upload files, format urls
        url, post_p, file_p, headers = await self._prepare_request(endpoint, *args, **kwargs)
        return await self.httpx_client.post(url=url, params=post_p, files=file_p, headers=headers, timeout=timeout)

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

    def get(self, url: str, callback: callable = None, delay: float = None, timeout: float = None) -> AsyncJob:
        """
        Makes a request to the given url with a get request.
        Adds the authorization header if an api key is configured for the request handler.
        :param url: The url to make the get request to. Can be a relative path.
        :param delay: The delay in seconds before the request is sent.
        :param timeout: The timeout in seconds of the request.
        :param callback: The callback function to call when the request is done.
        :return: An AsyncJob object that can be used to get the result of the request.
        """
        if "http" not in url:
            url = self.service_address.url + url

        headers = self._add_authorization_to_headers()
        req_coroutine = self.httpx_client.get(url=url, headers=headers, timeout=timeout)
        return self.async_job_manager.submit(req_coroutine, callback=callback, delay=delay)
