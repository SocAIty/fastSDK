import json
from typing import Union, Optional

from fastCloud import FastCloud, ReplicateUploadAPI
from fastsdk.jobs.async_jobs.async_job_manager import AsyncJobManager
from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.definitions.service_adress import ServiceAddress
from fastsdk.web.req.request_handler import RequestHandler, RequestData
from media_toolkit import MediaDict


class RequestHandlerReplicate(RequestHandler):
    """
    Works with Replicate API. https://replicate.com/docs/topics/predictions/create-a-prediction
    """
    def __init__(
            self,
            service_address: str | ServiceAddress | None,
            async_job_manager: Optional[AsyncJobManager] = None,
            api_key: Optional[str] = None,
            fast_cloud: Optional[Union[ReplicateUploadAPI, FastCloud]] = None,
            upload_to_cloud_threshold_mb: Optional[float] = 3,
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

    def _build_request_url(self, endpoint: EndPoint, query_params: dict | None = None) -> str:
        # Overwrites the default implementation, because /endpoint_route is not attached.
        # Also query_parameters are added to body not to url.
        # (replicate always just has 1 endpoint)
        return self.service_address.url

    async def _prepare_request_params(self, endpoint: EndPoint, *args, **kwargs) -> RequestData:
        """Prepare request parameters for Replicate API."""
        request_data = await super()._prepare_request_params(endpoint, *args, **kwargs)

        # Convert file_params to MediaDict if needed
        if request_data.file_params and not isinstance(request_data.file_params, MediaDict):
            request_data.file_params = MediaDict(request_data.file_params)

        # replicates expects query params to be in body also
        if request_data.query_params:
            request_data.body_params.update(request_data.query_params)

        # replicate formats the body as json with {"input": body_params, "version?": model_version}
        request_data.body_params = {"input": request_data.body_params}
        # Add version parameter for community models to get params to make predictions
        version = getattr(self.service_address, "version", None)
        if request_data.url and "/predictions" in request_data.url and version:
            request_data.body_params['version'] = version

        request_data.body_params = json.dumps(request_data.body_params)

        return request_data
