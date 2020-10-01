from google.oauth2 import id_token
import json
import google.auth
import google.auth.transport.requests
from google.auth.transport.requests import AuthorizedSession
from google.auth import compute_engine
import os


def get_keys(request):
    GSA = os.environ['GSA']
    cloud_run_invoker_GSA = os.environ['cloud_run_invoker_GSA']
    cloud_run_url = os.environ['cloud_run_url']

    google_oauth_reqest = google.auth.transport.requests.Request()
    target_audience = cloud_run_url
    url = "{url}/gsas/{GSA}/keys".format(url=target_audience, GSA=GSA)
    creds = compute_engine.IDTokenCredentials(google_oauth_reqest, target_audience=target_audience,
                                              service_account_email=cloud_run_invoker_GSA)

    authed_session = AuthorizedSession(creds)
    gsa_key_manager_response = authed_session.get(url)
    google_oauth_reqest = google.auth.transport.requests.Request()

    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }
    response = {
        url: gsa_key_manager_response.json(),
        'identity_token': creds.token,
        'Open ID Connect token verification': id_token.verify_token(creds.token, google_oauth_reqest)
    }

    return json.dumps(response), gsa_key_manager_response.status_code, headers
