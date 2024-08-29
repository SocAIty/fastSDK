from fastsdk.web.req.cloud_storage.i_cloud_storage import CloudStorage
from fastsdk.web.req.cloud_storage.azure_storage import AzureBlobStorage
from fastsdk.web.req.cloud_storage.s3_storage import S3Storage

def create_cloud_storage(
        # for azure
        azure_sas_access_token: str = None,
        azure_connection_string: str = None,
        # for s3
        s3_endpoint_url: str = None,
        s3_access_key_id: str = None,
        s3_access_key_secret: str = None
) -> CloudStorage:
    """
    Creates a cloud storage instance based on the configuration.
    """
    if azure_sas_access_token or azure_connection_string:
        return AzureBlobStorage(sas_access_token=azure_sas_access_token, connection_string=azure_connection_string)

    if s3_endpoint_url or s3_access_key_id or s3_access_key_secret:
        return S3Storage(s3_endpoint_url, s3_access_key_id, s3_access_key_secret)

    raise ValueError("Either provide Azure or S3 configuration to create a cloud storage instance.")