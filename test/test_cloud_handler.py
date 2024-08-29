import os

from fastsdk.web.req.cloud_storage.azure_storage import AzureBlobStorage

azure_container_connection_string = os.getenv("AZURE_CONTAINER_CONNECTION_STRING", None)
aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", None)

# to get this go to the
# azure portal -> containers -> Access Control -> Shared access tokens and generate one for your purpose
# here the url needs to be copied.

def test_azure():
    ch = AzureBlobStorage(sas_url_admin)
    fl = ch.upload(file="fries_maker/test_media/test_face_2.jpg")
    print(fl)

test_azure()