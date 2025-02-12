import json
from typing import Union

from fastCloud import FastCloud, ReplicateUploadAPI
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.service_adress import ServiceAddress
from fastsdk.web.req.request_handler import RequestHandler


class RequestHandlerReplicate(RequestHandler):
    """
    Works with Replicate API. https://replicate.com/docs/topics/predictions/create-a-prediction
    """
    def __init__(
            self,
            service_address: Union[str, ServiceAddress],
            async_job_manager: AsyncJobManager = None,
            api_key: str = None,
            fast_cloud: Union[ReplicateUploadAPI, FastCloud] = None,
            upload_to_cloud_threshold_mb: float = 3,
            *args, **kwargs
        ):

        if isinstance(upload_to_cloud_threshold_mb, str):
            try:
                upload_to_cloud_threshold_mb = float(upload_to_cloud_threshold_mb)
            except ValueError:
                upload_to_cloud_threshold_mb = 3

        if not isinstance(upload_to_cloud_threshold_mb, float) and not isinstance(upload_to_cloud_threshold_mb, int):
            upload_to_cloud_threshold_mb = 3

        super().__init__(
            service_address=service_address,
            async_job_manager=async_job_manager,
            fast_cloud=fast_cloud,
            upload_to_cloud_threshold_mb=upload_to_cloud_threshold_mb,
            api_key=api_key,
            *args, **kwargs
        )
        # replicate expects the files to be in base64 format in the input post parameter.
        # setting the value changes the behavior of the _upload_files method
        self._attached_files_format = 'base64'
        self._attach_files_to = 'body'

    def _prepare_request_url(self, endpoint: EndPoint, query_params: dict = None) -> str:
        # Overwrites the default implementation, because /endpoint_route is not attached.
        # (replicate always just has 1 endpoint)
        return self.service_address.url

    async def _request_endpoint(
            self,
            url: Union[str, None],
            query_params: Union[dict, None],
            body_params: Union[dict, None],
            file_params: Union[dict, None],
            headers: Union[dict, None],
            timeout: float,
            endpoint: EndPoint
    ):
        # Strategy:
        # Official models '/models/' -> Normal post request
        # Deployment '/deployments/' -> Normal post request
        # Community models '/predictions'/ -> Add version parameter and is get request
        # Refresh call '/predictions?job_id=' -> Get request

        # replicate wants file params attached to body as base64 or url
        if file_params:
            body_params.update(file_params)

        # replicates expects query params to be in body also
        if query_params:
            body_params.update(query_params)

        # replicate formats the body as json with {"input": body_params, "version?": model_version}
        body_params = {"input": body_params}
        # Add version parameter for community models to get params to make predictions
        version = getattr(self.service_address, "version", None)
        if "/predictions" in url and version:
            body_params['version'] = version

        # replicate requires the data to be a json input parameter
        data = json.dumps(body_params)
        return await self.httpx_client.post(url=url, data=data, headers=headers, timeout=timeout)


