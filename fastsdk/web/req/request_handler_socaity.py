from typing import Union

from fastsdk.web.definitions.endpoint import EndPoint
from fastsdk.web.req.request_handler import RequestHandler
from media_toolkit import MediaFile


class RequestHandlerSocaity(RequestHandler):
    """
    Works with Socaity API: https://api.socaity.ai/docs
    """
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
        # Socaity expects all parameters except of files as query parameters.
        # Only files go in the body.
        url_files = {k: v for k, v in file_params.items() if MediaFile._is_url(v)}
        body_params.update(url_files)
        file_params = {k: v for k, v in file_params.items() if k not in url_files}
        file_params = None if len(file_params) == 0 else file_params

        return await self.httpx_client.post(
            url=url, params=query_params, data=body_params, files=file_params, headers=headers,
            timeout=endpoint.timeout
        )

