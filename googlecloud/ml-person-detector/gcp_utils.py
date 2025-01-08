# upload detected images to GCS buckets in a async thread
from google.cloud import storage


def gcs_upload_blob(bucket_name, source_file_name, destination_blob_name):
    """
    Uploads a file to the bucket.
    :param bucket_name: Google cloud storage bucket name
    :param source_file_name: /local/path/to/file.png
    :param destination_blob_name: folder-path/storage-object-name.png
    :return: gs://bucket_name/destination_blob_name
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        # Optional: set a generation-match precondition to avoid potential race conditions
        # and data corruptions. The request to upload is aborted if the object's
        # generation number does not match your precondition. For a destination
        # object that does not yet exist, set the if_generation_match precondition to 0.
        # If the destination object already exists in your bucket, set instead a
        # generation-match precondition using its generation number.
        generation_match_precondition = 0

        blob.upload_from_filename(source_file_name, if_generation_match=generation_match_precondition)
        gs_path = f"gs://{bucket_name}/{destination_blob_name}"

        return gs_path

    except Exception as e:
        sys.stderr.write(
            f"Google Cloud Storage upload failed for {source_file_name} to {destination_blob_name} in bucket {bucket_name}: {e}!\n")  # Log or handle
        return None  # Or return a specific error value


def gcs_path_to_http_url(gcs_path):
    """Converts a Google Cloud Storage path to a publicly accessible HTTP URL.

    Args:
        gcs_path: The Google Cloud Storage path (e.g., gs://bucket/path/to/file.txt)

    Returns:
        A publicly accessible HTTP URL for the GCS object,
        or None if the path is not valid.

    Raises:
        ValueError: If the GCS path is not formatted correctly.
    """

    # Check if the path starts with "gs://"
    if not gcs_path.startswith("gs://"):
        raise ValueError("Invalid GCS path. Must start with 'gs://'")

    # Extract bucket and object names
    parts = gcs_path.split("/", 3)
    if len(parts) < 4:
        raise ValueError("Invalid GCS path format")

    bucket_name = parts[2]
    object_name = "/".join(parts[3:])

    # Publicly accessible objects don't require additional configuration
    return f"https://storage.cloud.google.com/{bucket_name}/{object_name}"
