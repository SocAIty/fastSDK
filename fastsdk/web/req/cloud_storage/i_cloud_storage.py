import io
from typing import Union, Optional

from media_toolkit import MediaFile


class CloudHandler:

    def upload(
            self,
            file: Union[bytes, io.BytesIO, MediaFile, str],
            file_name: str = None,
            folder: Optional[str] = None
    ) -> Union[str, None]:
        """
        Uploads a file to the cloud storage.
        :param file: The file data to upload. Is parsed to MediaFile if not already.
        :param file_name: The name of the file on the cloud storage. If None an uuid is generated.
        :param folder: Azure container-name or S3 bucket-name to upload the file to. If none default is used.
        :return: The URL of the uploaded file.
        """
        raise NotImplementedError("Implement in subclass")

    def download(self, url: str, save_path: str = None) -> Union[MediaFile, None, str]:
        """
        Downloads a file from the cloud storage.
        :param url: The URL of the file to download.
        :param save_path: The path to save the downloaded file to. If None a BytesIO object is returned.
        """
        raise NotImplementedError("Implement in subclass")

    def delete(self, url: str) -> bool:
        """
        Deletes a file from the cloud storage.
        :param url: The URL of the file to delete.
        :return: True if the file was deleted successfully
        """
        raise NotImplementedError("Implement in subclass")