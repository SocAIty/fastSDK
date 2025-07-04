from typing import Optional, Union
from fastCloud import FastCloud
from fastCloud.core import BaseUploadAPI
from media_toolkit import MediaDict


class FileHandler:
    def __init__(self, fast_cloud: FastCloud = None, upload_to_cloud_threshold_mb: float = None, max_upload_file_size_mb: float = None, file_format: str = 'httpx'):  
        """
        Initialize the FileHandler with optional FastCloud instance and upload thresholds.
        If not provided, the file handler will just return the files as MediaDict.
        """
        self.fast_cloud = fast_cloud
        self.upload_to_cloud_threshold_mb = upload_to_cloud_threshold_mb
        self.max_upload_file_size_mb = max_upload_file_size_mb
        self._attached_files_format = file_format or 'httpx'

    async def load_files_from_disk(self, file_params: dict) -> Union[MediaDict, dict]:
        """Load files from disk but ignore files that are provided as URLs"""
        media_files = MediaDict(files=file_params, download_files=False, read_system_files=True)
        return media_files

    async def _handle_file_upload(self, files: MediaDict) -> Optional[MediaDict | dict]:
        """
        Uploads the files based on different upload strategies:
        (1) If the cloud handler is not set:
            - files are either converted to base64 or httpx based on the _attached_files_format setting.
            - else the files are attached as files in httpx.
        (2) If the cloud handler is set:
            - If the combined file size is below the limit, the files are attached using method (1)
            - If the combined file size is above the limit, the files are uploaded using the cloud handler.

        Args:
            files: The files to be uploaded.
            
        Returns:
            - None: If no files were provided.
            - dict: files as provided if threshold is not met or no cloud handler is set.
            - dict: If files were uploaded. The dict is formatted as { file_name: download_url }.
            - dict: If files are attached. The dict contains the files in a format that can be sent with httpx.
        """
        if not files or len(files) == 0:
            return None

        total_size = files.file_size('mb')
        if self.max_upload_file_size_mb and total_size > self.max_upload_file_size_mb:
            raise ValueError(f"File size exceeds limit of {self.max_upload_file_size_mb}MB")

        if not self.fast_cloud or not self.upload_to_cloud_threshold_mb or total_size < self.upload_to_cloud_threshold_mb:
            return files

        if isinstance(self.fast_cloud, BaseUploadAPI):
            return await self.fast_cloud.upload_async(files)
        return self.fast_cloud.upload(files)

    def _get_non_url_files(self, files: MediaDict) -> MediaDict:
        if not files or len(files) == 0:
            return files
        
        if not isinstance(files, MediaDict):
            files = MediaDict(files=files, download_files=False, read_system_files=True)

        prevdownload_set = files.download_files
        files.download_files = False # could cause an infinite loop if it is true.
        sendable_files = files.get_processable_files(raise_exception=False, silent=True)
        files.download_files = prevdownload_set
        return sendable_files

    async def upload_files(self, files: MediaDict) -> Optional[MediaDict | dict]:
        sendable_files = self._get_non_url_files(files)
        # upload files to cloud if threshold is met and fastcloud is set
        uploaded_files = await self._handle_file_upload(sendable_files)
        files.update(uploaded_files)
        return files
        
    async def prepare_files_for_send(self, files: MediaDict) -> Optional[MediaDict | dict]:
        if not files or len(files) == 0:
            return files
        # get all files to be sent
        sendable_files = self._get_non_url_files(files)

        # convert to httpx format if threshold is not met and fastcloud is set
        if self._attached_files_format == 'httpx':
            return sendable_files.to_httpx_send_able_tuple()
        elif self._attached_files_format == 'base64':
            return sendable_files.to_base64()
        
        return sendable_files

