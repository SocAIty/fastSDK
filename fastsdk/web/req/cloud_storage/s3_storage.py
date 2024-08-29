# inspired by: https://github.com/runpod/runpod-python/blob/main/runpod/serverless/utils/rp_upload.py
import io
import multiprocessing
import time
from typing import Optional, Union
from urllib.parse import urlparse

from media_toolkit.utils.dependency_requirements import requires

try:
    import boto3
    from boto3 import session
    from boto3.s3.transfer import TransferConfig
    from botocore.config import Config
except ImportError:
    pass

from tqdm import tqdm

from fastsdk.web.req.cloud_storage.i_cloud_storage import CloudStorage


class S3Storage(CloudStorage):
    @requires("boto3")
    def __init__(
            self,
            endpoint_url: str = None,
            access_key_id: str = None,
            access_key_secret: str = None,
    ):

        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = access_key_secret

        self.transfer_config = TransferConfig(
            multipart_threshold=1024 * 25,
            max_concurrency=multiprocessing.cpu_count(),
            multipart_chunksize=1024 * 25,
            use_threads=True
        )

        self._boto_client = None

    def get_boto_client(self) -> boto3.client:
        """
        :returns: A boto3 client and transfer config for the bucket.
        """
        # Return the client if it already exists. Caching = Faster.
        if self._boto_client is not None:
            return self._boto_client

        if self.endpoint_url is None or self.access_key_id is None or self.secret_access_key is None:
            raise Exception("No or invalid bucket endpoint")

        # Extract region from the endpoint URL
        region = self.extract_region_from_url(self.endpoint_url)
        bucket_session = session.Session()
        boto_config = Config(
            signature_version='s3v4',
            retries={
                'max_attempts': 3,
                'mode': 'standard'
            }
        )
        boto_client = bucket_session.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=boto_config,
            region_name=region
        )

        return boto_client

    def upload_in_memory_object(
            self,
            file_name: str,
            file_data: Union[bytes, io.BytesIO],
            bucket_name: Optional[str] = None
    ) -> str:  # pragma: no cover
        """
        Uploads an in-memory object (bytes|BytesIO) to bucket storage and returns a presigned URL.
        :param file_name: The name of the file.
        :param file_data: The file data to upload.
        :param bucket_name: The name of the bucket to upload to (like directory name). If none: month-year is used.
        """
        boto_client = self.get_boto_client()

        if not bucket_name:
            bucket_name = time.strftime('%m-%y')

        if isinstance(file_data, io.BytesIO):
            file_data.seek(0)
        else:
            file_data = io.BytesIO(file_data)

        file_size = file_data.getbuffer().nbytes

        with tqdm(total=file_size, unit='B', unit_scale=True, desc=file_name) as progress_bar:
            boto_client.upload_fileobj(
                file_data,
                bucket_name,
                file_name,
                Config=self.transfer_config,
                Callback=progress_bar.update
            )
        # Reset the file pointer
        file_data.seek(0)

        presigned_url = boto_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_name
            },
            ExpiresIn=604800
        )

        return presigned_url

    @staticmethod
    def extract_region_from_url(endpoint_url):
        """
        Extracts the region from the endpoint URL.
        """
        parsed_url = urlparse(endpoint_url)
        # AWS/backblaze S3-like URL
        if '.s3.' in endpoint_url:
            return endpoint_url.split('.s3.')[1].split('.')[0]

        # DigitalOcean Spaces-like URL
        if parsed_url.netloc.endswith('.digitaloceanspaces.com'):
            return endpoint_url.split('.')[1].split('.digitaloceanspaces.com')[0]

        return None

    def download_file(self, url: str, save_path: str = None) -> str:
        boto_client = self.get_boto_client()
        # consider to use in memory download
        # boto_client.download_fileobj(url,)
        boto_client.download_file(url=url, destfile=save_path)
        return save_path
