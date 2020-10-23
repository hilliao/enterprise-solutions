import base64
import json
import os
import re

import google.auth
import google.auth.transport.requests
from google.auth import compute_engine
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore
from google.cloud import logging
from google.oauth2 import id_token

CLOUD_FUNC_KEY_DATA = 'data'
app_name = 'gsakeymanager-func'
gcp_logging_client = logging.Client()
gcp_logger = gcp_logging_client.logger(app_name)


# test publishing message to the topic:
# {"resource": {"parentDisplayName": "projects/$PROJECT_ID/serviceAccounts/sa@$PROJECT_ID.iam.gserviceaccount.com"}}
# method name needs to be the value of --entry-point in cloudbuild.yaml
def process_key(message, context):
    if context:
        print("""This Function was triggered by messageId {} published at {}""".format(context.event_id,
                                                                                       context.timestamp))

    if CLOUD_FUNC_KEY_DATA in message:
        data = base64.b64decode(message[CLOUD_FUNC_KEY_DATA]).decode('utf-8')
        gcp_logger.log_text(f"event dict data key has value: {data}", severity='DEBUG')
    else:
        raise LookupError(f"event dict does not contain data key: {message}")

    GSA_old_key_found = json.loads(data)
    key_resource = "resource"
    if not key_resource in GSA_old_key_found:
        raise LookupError(f"Security command center finding dict does not contain key {key_resource}")

    resource = GSA_old_key_found[key_resource]
    key_parentDisplayName = "parentDisplayName"
    if not key_parentDisplayName in resource:
        raise LookupError(f"Security command center finding dict does not contain key {key_parentDisplayName}")

    GSA_postfix = ".iam.gserviceaccount.com"
    GSA_REGEX = 'projects/([\w-]+)/serviceAccounts/([\w@-]+)' + GSA_postfix.replace(".", "\.") + '$'
    parentDisplayName = resource[key_parentDisplayName]
    regex_search_result = re.search(GSA_REGEX, parentDisplayName)
    if not regex_search_result or len(regex_search_result.groups()) != 2:
        raise ValueError(
            f"finding.{key_resource}.{key_parentDisplayName} failed to match regular expression {GSA_REGEX}")

    # check if the extracted Google service account is in the exclusion list
    GSA = regex_search_result.group(2) + GSA_postfix
    gcp_logger.log_text(f"extracted Google service account: {GSA}", severity='INFO')
    col = 'gsakeymanager'
    doc = 'func'
    key_ex = 'excluded'
    delimiter = ";"
    GSAs_excluded = []
    firebase_client = firestore.Client()
    snapshot_doc = firebase_client.collection(col).document(doc).get()
    doc = snapshot_doc.to_dict()
    if not doc:
        gcp_logger.log_text(f"Failed to load excluded list of Google service accounts at Firestore path /{col}/{doc}",
                            severity='ERROR')
        gcp_logger.log_text("Continuing without excluded list of Google service accounts", severity='WARNING')

    try:
        excluded = doc[key_ex]
        GSAs_excluded.extend(excluded.split(delimiter))
    except Exception as ex:
        gcp_logger.log_text(
            f"Firebase document does not have key: {key_ex} or its value can't be split by `{delimiter}`: {ex}",
            severity='ERROR')
        gcp_logger.log_text("Continuing without excluded list of Google service accounts", severity='WARNING')

    if GSA in GSAs_excluded:
        warning = f"{GSA} is in the excluded list"
        gcp_logger.log_text(warning, severity='WARNING')
        return warning

    # create an authenticated request to Cloud run GSA key manager for key rotation
    cloud_run_url = os.environ['CLOUD_RUN_URL']
    google_oauth_reqest = google.auth.transport.requests.Request()
    target_audience = cloud_run_url
    url = "{url}/gsas/{GSA}/keys".format(url=target_audience, GSA=GSA)

    # fails in local debugging if not executed in Google cloud function like environment
    creds = compute_engine.IDTokenCredentials(google_oauth_reqest,
                                              target_audience=target_audience,
                                              use_metadata_identity_endpoint=True)

    authed_session = AuthorizedSession(creds)
    gsa_key_manager_response = authed_session.get(url)
    google_oauth_reqest = google.auth.transport.requests.Request()

    responses = {
        url: gsa_key_manager_response.json(),
        'identity_token': creds.token,
        'Open ID Connect token verification': id_token.verify_token(creds.token, google_oauth_reqest)
    }

    gcp_logger.log_text(f"HTTP {gsa_key_manager_response.status_code}: {json.dumps(responses)}", severity='INFO')

    return gsa_key_manager_response.status_code, json.dumps(responses)


if __name__ == "__main__":
    msg = {
        "resource": {
            "parentDisplayName": f"projects/{os.environ['GSA_PROJ']}/serviceAccounts/{os.environ['GSA']}@{os.environ['GSA_PROJ']}.iam.gserviceaccount.com"
        }
    }
    encodedBytes = base64.b64encode(json.dumps(msg).encode('utf-8'))
    print(process_key({CLOUD_FUNC_KEY_DATA: encodedBytes}, None))
