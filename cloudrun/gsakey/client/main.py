# Credentials sample code from https://googleapis.dev/python/google-auth/1.7.0/user-guide.html#identity-tokens
# Invoking cloud run service with a Google service account key

from google.oauth2 import service_account
from google.oauth2 import id_token
import google.auth
import google.auth.transport.requests
from google.auth.transport.requests import AuthorizedSession
import os


def main():
    # base URL path of the cloud run service
    target_audience = os.environ['Cloud_Run_Service_Url']

    # Google service account to get the keys for
    GSA = os.environ['GSA']
    url = "{url}/gsakey/{GSA}".format(url=target_audience, GSA=GSA)

    # local file path to the Google service account key
    key_path = os.environ['KEY_PATH']
    creds = service_account.IDTokenCredentials.from_service_account_file(key_path, target_audience=target_audience)
    authed_session = AuthorizedSession(creds)

    # calling the cloud run service
    resp = authed_session.get(url)
    print('calling url {} returned {}'.format(url, resp.status_code))
    print('response body text: {}'.format(resp.text))

    # Open ID connect token verification
    request = google.auth.transport.requests.Request()
    token = creds.token
    print('open ID connect token: {}'.format(token))
    print('verifying token: {}'.format(id_token.verify_token(token, request)))


if __name__ == "__main__":
    main()
