"""Upload annotated frames to Google Cloud Storage and build the URL to view them in a browser."""
from google.cloud import storage
import sys


def upload_file(bucket_name, local_path, object_name):
    """
    Uploads a file to the bucket.
    :param bucket_name: Google cloud storage bucket name
    :param local_path: /local/path/to/file.png
    :param object_name: folder-path/storage-object-name.png
    :return: gs://bucket_name/object_name, or None if the upload failed
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        # Optional: set a generation-match precondition to avoid potential race conditions
        # and data corruptions. The request to upload is aborted if the object's
        # generation number does not match your precondition. For a destination
        # object that does not yet exist, set if_generation_match precondition to 0.
        # If the destination object already exists in your bucket, set instead a
        # generation-match precondition using its generation number.
        only_if_object_is_new = 0

        blob.upload_from_filename(local_path, if_generation_match=only_if_object_is_new)
        return f"gs://{bucket_name}/{object_name}"

    except Exception as error:
        sys.stderr.write(
            f"Google Cloud Storage upload failed for {local_path} to {object_name} in bucket {bucket_name}: {error}!\n")
        return None


def gcs_path_to_browser_url(gcs_path):
    """Converts a Google Cloud Storage path to a URL that opens the object in a browser.

    Args:
        gcs_path: The Google Cloud Storage path (e.g., gs://bucket/path/to/file.txt)

    Returns:
        https://storage.cloud.google.com/bucket/path/to/file.txt; opening it needs read access to the object.

    Raises:
        ValueError: If the GCS path is not formatted correctly.
    """

    # Check if the path starts with "gs://"
    if not gcs_path.startswith("gs://"):
        raise ValueError("Invalid GCS path. Must start with 'gs://'")

    # Extract bucket and object names
    path_parts = gcs_path.split("/", 3)
    if len(path_parts) < 4:
        raise ValueError("Invalid GCS path format")

    bucket_name = path_parts[2]
    object_name = path_parts[3]

    return f"https://storage.cloud.google.com/{bucket_name}/{object_name}"
