import base64
import json
import os
import sys
from datetime import datetime
from datetime import timedelta

import google.api_core.exceptions
import googleapiclient.discovery
import opencensus.trace.tracer
from flask import Flask
from flask import request
from gcloud import pubsub  # used to get project ID
from google.cloud import error_reporting
from google.cloud import logging
from google.cloud import secretmanager
from opencensus.ext.stackdriver import trace_exporter as stackdriver_exporter

HTTP_SERVER_ERROR = 500
HTTP_NOT_FOUND = 404

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


@app.route('/gsakey', methods=['POST'])
def post_gsa():
    """Creates a key for a service account; save the key's JSON secret to secret manager"""
    tracer = app.config['TRACER']
    with tracer.start_span(name=('%s-post' % app_name)) as span_method:

        form_key_gsa = 'gsa'
        if form_key_gsa not in request.form or not request.form[form_key_gsa]:
            return 'Missing form-data of key: {0} or value empty'.format(form_key_gsa), 400

        form_key_secret = 'secret_name'
        if form_key_secret not in request.form or not request.form[form_key_secret]:
            return 'Missing form-data of key: {0} or value empty'.format(form_key_secret), 400

        form_key_secret_manager_project_id = 'secret_manager_project_id'
        if form_key_secret_manager_project_id not in request.form \
                or not request.form[form_key_secret_manager_project_id]:
            secret_manager_project_id = gcp_project_id
        else:
            secret_manager_project_id = request.form[form_key_secret_manager_project_id]

        service_account_for_key = request.form[form_key_gsa]

        with span_method.span(name=('%s-post-creategsakey' % app_name)) as span_creategsakey:
            service = googleapiclient.discovery.build('iam', 'v1')

            key = service.projects().serviceAccounts().keys().create(
                name='projects/-/serviceAccounts/' + service_account_for_key, body={
                    'privateKeyType': 'TYPE_GOOGLE_CREDENTIALS_FILE'
                }).execute()

            gsa_key = base64.b64decode(key['privateKeyData'])
            gcp_logger.log_text(
                'POST {1}/gsakey created service account key {0} succeeded'.format(key['name'], app_name))

        # create a secret to store the service account key
        with span_method.span(name=('%s-post-managesecret' % app_name)) as span_managesecret:
            sm_client = secretmanager.SecretManagerServiceClient()

            # check if the secret exists
            secret_name = request.form[form_key_secret]
            secret_full_name = sm_client.secret_path(secret_manager_project_id, secret_name)
            find_secret_result = None

            try:
                try:
                    find_secret_result = sm_client.get_secret(request={"name": secret_full_name})
                    is_create_secret = False
                except google.api_core.exceptions.NotFound as secret_not_found:
                    is_create_secret = True
                    gcp_logger.log_text('POST {1}/gsakey secret {0} not found'.format(secret_full_name, app_name))

                create_secret_result = None
                # if the given secret not found, create the secret
                if is_create_secret:
                    parent = f"projects/{secret_manager_project_id}"
                    create_secret_result = sm_client.create_secret(request={
                        "parent": parent,
                        "secret_id": secret_name,
                        "secret": {"replication": {"automatic": {}}}
                    })

                    gcp_logger.log_text(
                        'POST {1}/gsakey secret {0} created'.format(create_secret_result.name, app_name))

                # update the secret version
                parent = sm_client.secret_path(secret_manager_project_id, secret_name)
                add_secret_ver_result = None
                add_secret_ver_result = sm_client.add_secret_version(
                    request={"parent": parent, "payload": {"data": gsa_key}}
                )
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
        if is_create_secret and create_secret_result:
            result['created_secret'] = create_secret_result.name
        if add_secret_ver_result:
            result['added_secret_version'] = add_secret_ver_result.name

    return result


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

    return delete_gsa_keys_base(full_sa_key_names)


def delete_gsa_keys_base(full_sa_key_names):
    tracer = app.config['TRACER']
    with tracer.start_span(name=('%s-delete' % app_name)) as span_method:
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

        gcp_logger.log_text('DELETE {1}/gsakey {0}'.format(keys_deleted, app_name))
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
    with tracer.start_span(name=('%s-get' % app_name)) as span_method:
        service_account_to_get = gsa
        service = googleapiclient.discovery.build('iam', 'v1')

        keys = service.projects().serviceAccounts().keys().list(
            name='projects/-/serviceAccounts/' + service_account_to_get).execute()
        gcp_logger.log_text('GET {1}/gsakey {0}'.format(service_account_to_get, app_name))

    return keys


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
