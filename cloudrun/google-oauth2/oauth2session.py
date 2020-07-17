# Google OAuth example from https://google-auth.readthedocs.io/en/latest/user-guide.html#user-credentials
# Python based microservice that accepts /login to redirect to Google account login page
# The redirect_uri is configured at https://console.developers.google.com/apis/credentials/oauthclient/998082892233-2jirst2cil7b8tcnku40v0q5cvns8f3a.apps.googleusercontent.com?project=acn-gcp-security
# The redirect_uri at /callback creates a Google credential from the OAuth2 session
# logging client library severity at https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#LogSeverity
# must add OAuth2 scope of https://www.googleapis.com/auth/cloud-platform
# To refresh or save tokens across sessions: https://requests-oauthlib.readthedocs.io/en/latest/examples/real_world_example_with_refresh.html

from requests_oauthlib import OAuth2Session
import os
from flask import Flask, request, redirect, session
from flask.json import jsonify
from google.cloud import logging
from google_auth_oauthlib.helpers import credentials_from_session
import googleapiclient.discovery
from google.cloud import datacatalog_v1
from gcloud import pubsub  # used to get project ID

gcp_logging_client = logging.Client()
app_name = 'oauth2sample'
gcp_logger = gcp_logging_client.logger(app_name)

authorization_base_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://www.googleapis.com/oauth2/v4/token"
client_id = '998082892233-k2fl9kdp2vg4kf77oru10uo5vepe32ip.apps.googleusercontent.com'

client_secret = os.environ.get('CLIENT_SECRET')

if os.environ.get('LOCAL_DEBUG'):
    redirect_uri = 'http://hil.freeddns.org:5000/callback'
else:
    redirect_uri = 'https://googleoauth2-zro2itatnq-uc.a.run.app/callback'
scope = ["https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile",
         "https://www.googleapis.com/auth/compute.readonly", 'https://www.googleapis.com/auth/cloud-platform']

app = Flask(__name__)

# highly recommend changing the secret key in production
app.secret_key = client_secret
# highly recommend not using debug mode in production
app.config['DEBUG'] = True

@app.route("/login")
def login():
    oauth2session = OAuth2Session(client_id, scope=scope, redirect_uri=redirect_uri)
    authorization_url, state = oauth2session.authorization_url(authorization_base_url)

    # State is used to prevent CSRF, keep this for later.
    session['oauth_state'] = state
    gcp_logger.log_text('OAuth state: ' + state, severity='INFO')
    gcp_logger.log_text('redirecting to: ' + authorization_url, severity='WARNING')

    return redirect(authorization_url)


def list_instances(creds):
    compute = googleapiclient.discovery.build(serviceName='compute', version='v1', credentials=creds)
    pubsub_client = pubsub.Client()
    gcp_project_id = pubsub_client.project

    result = compute.zones().list(project=gcp_project_id).execute()
    return result['items'] if 'items' in result else None


@app.route("/callback")
def callback():
    oauth2_session = OAuth2Session(client_id, state=session['oauth_state'], redirect_uri=redirect_uri)
    token = oauth2_session.fetch_token(token_url, client_secret=client_secret, authorization_response=request.url)

    gcp_logger.log_text('OAuth2 token type: ' + token['token_type'], severity='DEBUG')
    gcp_logger.log_text('Test logging client_id as error: ' + oauth2_session.client_id, severity='ERROR')

    # use the session to store the token
    session['oauth_token'] = token

    return jsonify(oauth2_session.token)


@app.route("/sampleentry")
def sampleentry():
    oauth2_session = OAuth2Session(client_id, token=session['oauth_token'])
    google_auth_credentials = credentials_from_session(oauth2_session)
    datacatalog = datacatalog_v1.DataCatalogClient(credentials=google_auth_credentials)

    resource_name = '//bigquery.googleapis.com/projects/{}/datasets/{}' \
                    '/tables/{}' \
        .format('bigquery-public-data', 'covid19_usafacts', 'summary')

    data_catalog_entry = datacatalog.lookup_entry(linked_resource=resource_name)
    return str(data_catalog_entry)


@app.route("/entry/projects/<project_id>/datasets/<dataset>/tables/<table>")
def entry(project_id, dataset, table):
    oauth2_session = OAuth2Session(client_id, token=session['oauth_token'])
    google_auth_credentials = credentials_from_session(oauth2_session)
    datacatalog = datacatalog_v1.DataCatalogClient(credentials=google_auth_credentials)

    resource_name = '//bigquery.googleapis.com/projects/{}/datasets/{}' \
                    '/tables/{}' \
        .format(project_id, dataset, table)

    data_catalog_entry = datacatalog.lookup_entry(linked_resource=resource_name)
    return str(data_catalog_entry)


@app.route("/zones")
def zones():
    oauth2_session = OAuth2Session(client_id, token=session['oauth_token'])
    google_auth_credentials = credentials_from_session(oauth2_session)
    zones = list_instances(google_auth_credentials)
    return jsonify(zones)


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
