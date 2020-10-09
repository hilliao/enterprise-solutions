from google.oauth2 import id_token
import json
import google.auth
import google.auth.transport.requests
from google.auth.transport.requests import AuthorizedSession
from google.auth import compute_engine
import os
import base64
import re

KEY_DATA = 'data'


def process_key(message, context):
    if context:
        print("""This Function was triggered by messageId {} published at {}""".format(context.event_id,
                                                                                       context.timestamp))

    if KEY_DATA in message:
        data = base64.b64decode(message[KEY_DATA]).decode('utf-8')
        print(f"event dict data key has value: {data}")
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

    GSA = regex_search_result.group(2) + GSA_postfix
    print(f"extracted Google service account: {GSA}")
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

    print(f"HTTP {gsa_key_manager_response.status_code}: {json.dumps(responses)}")

    return gsa_key_manager_response.status_code, json.dumps(responses)


if __name__ == "__main__":
    msg = {
        "resource": {
            "parentDisplayName": f"projects/{os.environ['GSA_PROJ']}/serviceAccounts/{os.environ['GSA']}@{os.environ['GSA_PROJ']}.iam.gserviceaccount.com"
        }
    }
    encodedBytes = base64.b64encode(json.dumps(msg).encode('utf-8'))
    print(process_key({KEY_DATA: encodedBytes}, None))
