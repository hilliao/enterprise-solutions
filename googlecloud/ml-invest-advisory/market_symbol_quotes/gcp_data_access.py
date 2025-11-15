from google.cloud import secretmanager
import os


def get_gcp_secret(secret_id: str):
    """
    Accesses a secret from Google Cloud Secret Manager.

    Args:
        secret_id: The ID of the secret to access.

    Returns:
        The secret value that needs calling `.data.decode("UTF-8")`
    """

    client = secretmanager.SecretManagerServiceClient()
    secret_version_name = client.secret_path(os.environ["PROJECT_ID"], secret_id) + "/versions/latest"
    request = {"name": secret_version_name}
    response = client.access_secret_version(request)
    return response.payload
