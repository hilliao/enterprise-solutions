'''
Google cloud storage upload sample
install python3 modules: sudo -H pip3 install --upgrade google-cloud ; ref at https://googlecloudplatform.github.io/google-cloud-python/
Run gcloud auth application-default login at the command prompt ; ref at https://googlecloudplatform.github.io/google-cloud-python/stable/google-cloud-auth.html
code inspired from http://stackoverflow.com/questions/37003862/google-cloud-storage-how-to-upload-a-file-from-python-3
'''

from google.cloud import storage

# upload a file to the bucket
client = storage.Client(project='hil-micro-use')
bucket=client.get_bucket('hilbucket')
blobfile = 'app-release.apk'
blob = bucket.blob(blobfile)
blob.upload_from_filename('~/' + blobfile)

# make the file accessible publicly
acl = blob.acl
acl.all().grant_read()
acl.save()
acl.get_entities()


'''
Azure blob storage upload sample
install python3 modules: sudo -H pip3 install azure-storage
code inspired from https://docs.microsoft.com/en-us/azure/storage/storage-python-how-to-use-blob-storage
'''

from azure.storage.blob import ContentSettings
from azure.storage.blob import PublicAccess
from azure.storage.blob import BlockBlobService

block_blob_service = BlockBlobService(account_name='blockblob', account_key='X8DVDsVTQLKngOcKeUb8IdsLoiX8/rZ7tx9IShBSf/2me6xuvHHYC53Sdwm1qRjrmXRXSGJ45ssL/5Yv/m/A9Q==')
container = list(block_blob_service.list_containers())[0]
container.name
block_blob_service.set_container_acl('shared', public_access=PublicAccess.Container)
block_blob_service.create_blob_from_path(container.name, 'en_office_professional_plus_2013_with_sp1_x64_dvd_3928183.iso', '/home/hil/Downloads/en_office_professional_plus_2013_with_sp1_x64_dvd_3928183.iso', content_settings=ContentSettings(content_type='application/octet-stream'))