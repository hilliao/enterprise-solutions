import base64
import json
import os
import re
import sys
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent import futures
from datetime import datetime
from datetime import timedelta

import google.api_core.exceptions
import googleapiclient.discovery
import opencensus.trace.tracer
from flask import Flask, jsonify
from flask import request
from gcloud import pubsub  # used to get project ID
from google.cloud import error_reporting
from google.cloud import logging
from google.cloud import secretmanager
from opencensus.ext.stackdriver import trace_exporter as stackdriver_exporter

HTTP_BAD_REQUEST = 400
HTTP_SERVER_ERROR = 500
HTTP_NOT_FOUND = 404
HTTP_MULTI_STATUS = 207

app_name = 'gsakeymanager'

try:
    import googleclouddebugger

    googleclouddebugger.enable()
except:
    for e in sys.exc_info():
        print(e)


def initialize_tracer(project_id):
    exporter = stackdriver_exporter.StackdriverExporter(
        project_id=project_id
    )
    tracer = opencensus.trace.tracer.Tracer(
        exporter=exporter,
        sampler=opencensus.trace.tracer.samplers.AlwaysOnSampler()
    )

    return tracer


app = Flask(__name__)

# if debugging or running on localhost
if __name__ == "__main__":
    gcp_project_id = os.environ['GCP_PROJECT']
# running in Google Cloud Run
else:
    pubsub_client = pubsub.Client()
    gcp_project_id = pubsub_client.project

gcp_tracer = initialize_tracer(gcp_project_id)
app.config['TRACER'] = gcp_tracer
gcp_logging_client = logging.Client()
gcp_logger = gcp_logging_client.logger(app_name)
error_reporting_client = error_reporting.Client()


@app.route('/health', methods=['GET'])
def health_check():
    import flask
    return 'Running Flask {0} on Python {1}!\n'.format(flask.__version__, sys.version)


# show uncaught exceptions in the response body from deployed service
if __name__ != "__main__":
    @app.errorhandler(Exception)
    def handle_uncaught_exception(err):
        error_reporting_client.report_exception()
        # Pass http errors to the client with the given HTTP code
        if isinstance(err, googleapiclient.errors.HttpError):
            return str(err), err.resp.status

        if isinstance(err, google.api_core.exceptions.GoogleAPIError):
            return str(err), err.code

        # handling non-HTTP exceptions only
        return str(err), HTTP_SERVER_ERROR


@app.route('/rotate_days_old/<days>', methods=['POST'])
def rotate(days):
    """
    Accept a list of Google service accounts, a floating point number of days old keys to delete
    Args:
        GCP_SAs (header form-data): Google Service Account separated by ,
        secret_name_prefix (header form-data): prefix of secret ID in secret manager
        secret_manager_project_id (header form-data): secret manager's PROJECT ID
        days (path parameter): floating point number of days; 0 means don't delete keys

    Returns:
        207:
        Each thread completed; see the thread result['error'] for any error in the response JSON array
    """
    days_float = float(days)
    # parsing the form-data from the request header
    form_key_GCP_SAs = 'GCP_SAs'
    if form_key_GCP_SAs not in request.form or not request.form[form_key_GCP_SAs]:
        return 'Missing form-data of key: {0} or value empty'.format(form_key_GCP_SAs), HTTP_BAD_REQUEST

    form_key_secret_prefix = 'secret_name_prefix'
    if form_key_secret_prefix not in request.form or not request.form[form_key_secret_prefix]:
        return 'Missing form-data of key: {0} or value empty'.format(form_key_secret_prefix), HTTP_BAD_REQUEST
    else:
        secret_name_prefix = request.form[form_key_secret_prefix]

    form_key_secret_manager_project_id = 'secret_manager_project_id'
    if form_key_secret_manager_project_id not in request.form \
            or not request.form[form_key_secret_manager_project_id]:
        secret_manager_project_id = gcp_project_id
    else:
        secret_manager_project_id = request.form[form_key_secret_manager_project_id]

    service_accounts = request.form[form_key_GCP_SAs].split(",")
    if len([sa for sa in service_accounts if "@" in sa and ".iam.gserviceaccount.com" in sa]) < len(service_accounts):
        return f"Google service accounts in form-data of key {form_key_GCP_SAs} isn't in the format" \
               f" *@*.iam.gserviceaccount.com", HTTP_BAD_REQUEST

    tracer = app.config['TRACER']
    with tracer.start_span(name=f"{app_name}:rotate") as span_rotate_key:
        def gen_key_put_secret(GCP_SA):
            with span_rotate_key.span(name=f"{app_name}:rotate.gen_key({GCP_SA})") as span_gen_key:
                try:
                    GCP_SA_PROJECT_ID_search_result = re.search('(.*)@(.*)\.iam\.gserviceaccount\.com', GCP_SA)
                    GCP_SA_Name = GCP_SA_PROJECT_ID_search_result.group(1)
                    GCP_SA_PROJECT_ID = GCP_SA_PROJECT_ID_search_result.group(2)
                    gsa_key = gen_key(GCP_SA)
                    secret_id = secret_name_prefix + GCP_SA_PROJECT_ID + "_" + GCP_SA_Name
                except Exception as ex:
                    error_reporting_client.report_exception()
                    return {
                        'error': str(ex)
                    }

                GCP_SA_dict = json.loads(gsa_key)

            with span_rotate_key.span(name=f"{app_name}:rotate.put_secret({secret_id})") as span_put_secret:
                try:
                    find_secret_result, create_secret_result, add_secret_ver_result = put_secret(gsa_key,
                                                                                                 secret_manager_project_id,
                                                                                                 secret_id)
                except Exception as ex:
                    error_reporting_client.report_exception()
                    key_name = f"projects/{GCP_SA_PROJECT_ID}/serviceAccounts/{GCP_SA}/keys/{GCP_SA_dict['private_key_id']}"
                    key_op = delete_gsa_keys_base([key_name])
                    key_op['created'] = GCP_SA_dict
                    gcp_logger.log_text(
                        f"{app_name}:rotate Failed to put secret for {GCP_SA_dict['client_email']}'s"
                        f" key {GCP_SA_dict['private_key_id']}, which was created then deleted",
                        severity='WARNING')
                    result = {
                        'error': str(ex),
                        'handled': 'Google service account key created but could not put secret; key deleted',
                        'keys': key_op
                    }
                    return result

                response = GCP_SA_dict
                if find_secret_result:
                    response['found_secret'] = find_secret_result.name
                if not find_secret_result and create_secret_result:
                    response['created_secret'] = create_secret_result.name
                if add_secret_ver_result:
                    response['added_secret_version'] = add_secret_ver_result.name

            if days_float > 0:
                with span_rotate_key.span(name=f"{app_name}:rotate.delete_old_keys({GCP_SA})") as span_delete_old_keys:
                    try:
                        deletion_result = delete_gsa_keys_days_older(GCP_SA, days_float)
                        response.update(deletion_result)
                    except Exception as ex:
                        error_reporting_client.report_exception()
                        return {
                            'error': str(ex)
                        }

            return response

        with ThreadPoolExecutor(max_workers=20) as executor:
            threads = [executor.submit(gen_key_put_secret, GCP_SA) for GCP_SA in service_accounts]
            futures.wait(threads, return_when=futures.ALL_COMPLETED)

    if days_float > 0:
        gcp_logger.log_text(
            f"{app_name}:rotate Rotated keys of Google service accounts: {request.form[form_key_GCP_SAs]}",
            severity='INFO')
    else:
        gcp_logger.log_text(
            f"{app_name}:rotate Generated keys of Google service accounts: {request.form[form_key_GCP_SAs]}",
            severity='INFO')

    return jsonify([t.result() for t in threads]), HTTP_MULTI_STATUS


@app.route('/gsakey', methods=['POST'])
def post_gsa():
    """Creates a key for a service account; save the key's JSON secret to secret manager
       Args:
            gsa (header form-data): Google Service Account.
            secret_name (header form-data): secret ID in secret manager
            secret_manager_project_id (header form-data): secret manager's PROJECT ID

        Returns:
            HTTP OK:
            JSON of the following format
            {
                "added_secret_version": "projects/PROJECT_NUMBER/secrets/SECRET_ID/versions/VER_NUMBER",
                "private_key": "-----BEGIN PRIVATE ",
                "found_secret": "",
                "created_secret": ""
            },
            OR ON ERROR:
            {
                'error': str(ex),
                'warning': 'Action needed:',
                'created': json.loads(gsa_key)
            }
    """
    # parsing the form-data from the request header
    form_key_gsa = 'gsa'
    if form_key_gsa not in request.form or not request.form[form_key_gsa]:
        return 'Missing form-data of key: {0} or value empty'.format(form_key_gsa), 400

    form_key_secret = 'secret_name'
    if form_key_secret not in request.form or not request.form[form_key_secret]:
        return 'Missing form-data of key: {0} or value empty'.format(form_key_secret), 400
    else:
        secret_name = request.form[form_key_secret]

    form_key_secret_manager_project_id = 'secret_manager_project_id'
    if form_key_secret_manager_project_id not in request.form \
            or not request.form[form_key_secret_manager_project_id]:
        secret_manager_project_id = gcp_project_id
    else:
        secret_manager_project_id = request.form[form_key_secret_manager_project_id]

    service_account_for_key = request.form[form_key_gsa]

    tracer = app.config['TRACER']
    with tracer.start_span(name=('%s-post' % app_name)) as span_method:
        # generate a Google service account key
        with span_method.span(name=('%s-post-creategsakey' % app_name)) as span_creategsakey:
            gsa_key = gen_key(service_account_for_key)

        # create a secret to store the service account key
        with span_method.span(name=('%s-post-managesecret' % app_name)) as span_managesecret:
            try:
                find_secret_result, create_secret_result, add_secret_ver_result = put_secret(gsa_key,
                                                                                             secret_manager_project_id,
                                                                                             secret_name)
            except Exception as ex:
                error_reporting_client.report_exception()
                err_resp = {
                    'error': str(ex),
                    'warning': 'Action needed: created Service Account key but failed to ingest secrets; ingest manually or delete the key',
                    'created': json.loads(gsa_key)
                }
                if isinstance(ex, google.api_core.exceptions.GoogleAPIError):
                    return err_resp, ex.code
                else:
                    return err_resp, HTTP_SERVER_ERROR

            gcp_logger.log_text('POST {1}/gsakey secret {0} version added'.format(add_secret_ver_result.name, app_name))

        result = json.loads(gsa_key)
        if find_secret_result:
            result['found_secret'] = find_secret_result.name
        if not find_secret_result and create_secret_result:
            result['created_secret'] = create_secret_result.name
        if add_secret_ver_result:
            result['added_secret_version'] = add_secret_ver_result.name

    return result


def gen_key(service_account_for_key):
    service = googleapiclient.discovery.build('iam', 'v1')
    key = service.projects().serviceAccounts().keys().create(
        name='projects/-/serviceAccounts/' + service_account_for_key, body={
            'privateKeyType': 'TYPE_GOOGLE_CREDENTIALS_FILE'
        }).execute()
    gsa_key = base64.b64decode(key['privateKeyData'])
    gcp_logger.log_text(f"{app_name}:gen_key created service account key succeeded: {key['name']}", severity='INFO')
    return gsa_key


def put_secret(gsa_key, secret_manager_project_id, secret_name):
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        secret_full_name = sm_client.secret_path(secret_manager_project_id, secret_name)

        # check if the secret exists
        find_secret_result_local = sm_client.get_secret(request={"name": secret_full_name})
    except google.api_core.exceptions.NotFound as secret_not_found:
        find_secret_result_local = None
        gcp_logger.log_text(f"{app_name}:put_secret secret {secret_full_name} not found", severity='DEBUG')
    # if the given secret not found, create the secret
    if not find_secret_result_local:
        parent = f"projects/{secret_manager_project_id}"
        create_secret_result_local = sm_client.create_secret(request={
            "parent": parent,
            "secret_id": secret_name,
            "secret": {"replication": {"automatic": {}}}
        })

        gcp_logger.log_text(f"{app_name}:put_secret secret {create_secret_result_local.name} created", severity='INFO')
    else:
        create_secret_result_local = None
    # update the secret version
    parent = sm_client.secret_path(secret_manager_project_id, secret_name)
    add_secret_ver_result_local = sm_client.add_secret_version(
        request={"parent": parent, "payload": {"data": gsa_key}}
    )

    return find_secret_result_local, create_secret_result_local, add_secret_ver_result_local


@app.route('/gsas/<gsa>/keys-days-older/<days>', methods=['DELETE'])
def delete_gsa_keys_days_older(gsa, days):
    keys_search_result = get_gsa_keys_days_older(gsa, days)
    if type(keys_search_result) is tuple:
        # something bad happened; the 2nd item is the HTTP status code
        return keys_search_result

    deletion_result = delete_gsa_keys_base(keys_search_result['names'])

    return deletion_result


@app.route('/gsakeys', methods=['DELETE'])
def delete_gsa_keys():
    """Delete GSA keys passed in the request form data as a list"""
    form_key = 'gsa-key-names'
    if form_key not in request.form or not request.form[form_key]:
        return 'Missing form-data of key: {0} or value empty'.format(form_key), 400

    full_sa_key_names = request.form[form_key].split(',')
    if len([sa_key_name for sa_key_name in full_sa_key_names if "keys/" in sa_key_name])<len(full_sa_key_names):
        return f"Google service account key in form-data of key {form_key} isn't in the format of " \
               f"projects/PROJECT_ID/serviceAccounts/sa@PROJECT_ID.iam.gserviceaccount.com/keys/key_name"

    return delete_gsa_keys_base(full_sa_key_names)


def delete_gsa_keys_base(full_sa_key_names):
    search_result = re.search('keys/(.*)', full_sa_key_names[0])
    key = search_result.group(1)
    tracer = app.config['TRACER']
    with tracer.start_span(name=f"{app_name}:delete_key({key})") as span_method:
        keys_deleted = []

        for full_sa_key_name in full_sa_key_names:
            service = googleapiclient.discovery.build('iam', 'v1')
            full_sa_key_name = full_sa_key_name.strip()
            try:
                service.projects().serviceAccounts().keys().delete(name=full_sa_key_name).execute()
            except Exception as ex:
                error_reporting_client.report_exception()
                err_resp = {
                    'error': str(ex),
                    'deleted': keys_deleted
                }
                if isinstance(ex, googleapiclient.errors.HttpError):
                    return err_resp, ex.resp.status
                else:
                    return err_resp, HTTP_SERVER_ERROR

            keys_deleted.append(full_sa_key_name)

        gcp_logger.log_text(f"{app_name}:delete_gsa_keys_base deleted {keys_deleted}", severity='INFO')
    return {'deleted': keys_deleted}


@app.route('/gsas/<gsa>/keys-days-older/<days>', methods=['GET'])
def get_gsa_keys_days_older(gsa, days):
    """Lists keys for a USER_MANAGED service account over days old.
        Args:
            gsa (str): Google Service Account.
            days (int): over given number of days old.

        Returns:
            keys of the Google Service Account over given number of days old:
            "keys": [
            {
                "keyAlgorithm": "KEY_ALG_RSA_2048",
                "keyOrigin": "GOOGLE_PROVIDED",
                "keyType": "SYSTEM_MANAGED",
                "name": "projects/[Project ID]/serviceAccounts/[name]@[Project ID].iam.gserviceaccount.com/keys/[key ID]",
                "validAfterTime": "2020-04-12T04:44:38Z",
                "validBeforeTime": "2020-04-29T04:44:38Z"
            }],
            "names": "projects/[Project ID]/serviceAccounts/gsa@[Project ID].iam.gserviceaccount.com/keys/ff00d4622af5e3e92df5633f95b7f2497a927514,projects/[Project ID]/serviceAccounts/gsa@[Project ID].iam.gserviceaccount.com/keys/5f58dbbc8b7f849bce9c24148dcfdc3f7917046b"
    """
    days_float = float(days)
    keys = get_gsa_keys(gsa)
    keys = [item for item in keys['keys'] if item['keyType'] == 'USER_MANAGED']
    if not keys:
        return {
                   'keys': [],
                   'names': []
               }, HTTP_NOT_FOUND

    days_older = [item for item in keys if
                  datetime.utcnow() - datetime.strptime(item['validAfterTime'], '%Y-%m-%dT%H:%M:%SZ') > timedelta(
                      days=days_float)]
    days_older_key_names = [item['name'] for item in days_older]
    names = days_older_key_names

    return {
        'keys': days_older,
        'names': names
    }


@app.route('/gsas/<gsa>/keys', methods=['GET'])
def get_gsa_keys(gsa):
    """Lists all keys for a service account.
    Args:
        gsa (str): Google Service Account.

    Returns:
        keys of the Google Service Account:
        "keys": [
        {
            "keyAlgorithm": "KEY_ALG_RSA_2048",
            "keyOrigin": "GOOGLE_PROVIDED",
            "keyType": "SYSTEM_MANAGED",
            "name": "projects/[Project ID]/serviceAccounts/[name]@[Project ID].iam.gserviceaccount.com/keys/[key ID]",
            "validAfterTime": "2020-04-12T04:44:38Z",
            "validBeforeTime": "2020-04-29T04:44:38Z"
        }]

    https://cloud.google.com/iam/docs/creating-managing-service-account-keys#iam-service-account-keys-create-python
    """
    tracer = app.config['TRACER']
    with tracer.start_span(name=f"{app_name}:get_key({gsa})") as span_method:
        service = googleapiclient.discovery.build('iam', 'v1')

        keys = service.projects().serviceAccounts().keys().list(name='projects/-/serviceAccounts/' + gsa).execute()
        names = [key['name'] for key in keys['keys']]
        gcp_logger.log_text(f"{app_name}:get_gsa_keys {names}", severity='INFO')

    return keys


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
