import os
import sys
import googleapiclient.discovery
from flask import Flask
from flask import jsonify
from flask import request
from google.cloud import logging
from gcloud import pubsub  # used to get project ID
import base64
import json
from opencensus.ext.stackdriver import trace_exporter as stackdriver_exporter
import opencensus.trace.tracer
from google.cloud import secretmanager
import google.api_core.exceptions
from google.cloud import error_reporting

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
def hello_world():
    import flask
    return 'Running Flask {0} on Python {1}!\n'.format(flask.__version__, sys.version)


@app.route('/gsakey', methods=['POST'])
def post_gsa():
    """Creates a key for a service account; save the key's JSON secret to secret manager"""
    tracer = app.config['TRACER']
    with tracer.span(name=('%s-post' % app_name)) as span_method:

        form_key_gsa = 'gsa'
        if form_key_gsa not in request.form or not request.form[form_key_gsa]:
            return 'Missing form-data of key: {0} or value empty'.format(form_key_gsa), 400

        form_key_secret = 'secret_name'
        if form_key_secret not in request.form or not request.form[form_key_secret]:
            return 'Missing form-data of key: {0} or value empty'.format(form_key_secret), 400

        form_key_secret_manager_project_id = 'secret_manager_project_id'
        if form_key_secret_manager_project_id not in request.form or not request.form[
            form_key_secret_manager_project_id]:
            secret_manager_project_id = gcp_project_id
        else:
            secret_manager_project_id = request.form[form_key_secret_manager_project_id]

        service_account_key_to_create = request.form[form_key_gsa]

        with span_method.span(name=('%s-post-creategsakey' % app_name)) as span_creategsakey:
            service = googleapiclient.discovery.build('iam', 'v1')

            try:
                key = service.projects().serviceAccounts().keys().create(
                    name='projects/-/serviceAccounts/' + service_account_key_to_create, body={
                        'privateKeyType': 'TYPE_GOOGLE_CREDENTIALS_FILE'
                    }).execute()
            except googleapiclient.errors.HttpError as err:
                err_result = json.loads(err.content.decode("utf-8"))
                return err_result, err.resp.status

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
                find_secret_result = sm_client.get_secret(secret_full_name)
                is_create_secret = False
            except google.api_core.exceptions.NotFound as err404:
                is_create_secret = True
                gcp_logger.log_text('POST {1}/gsakey secret {0} not found'.format(secret_full_name, app_name))
            except google.api_core.exceptions.PermissionDenied as err:
                error_reporting_client.report_exception()
                return str(err), err.code

            create_secret_result = None
            if is_create_secret:
                # if not found, create the secret
                parent = sm_client.project_path(secret_manager_project_id)
                try:
                    create_secret_result = sm_client.create_secret(parent, secret_name, {
                        'replication': {
                            'automatic': {},
                        },
                    })
                except (google.api_core.exceptions.PermissionDenied, google.api_core.exceptions.AlreadyExists) as err:
                    error_reporting_client.report_exception()
                    return str(err), err.code

                gcp_logger.log_text('POST {1}/gsakey secret {0} created'.format(create_secret_result.name, app_name))

            # update the secret version
            parent = sm_client.secret_path(secret_manager_project_id, secret_name)
            add_secret_ver_result = None
            try:
                add_secret_ver_result = sm_client.add_secret_version(parent, {'data': gsa_key})
            except google.api_core.exceptions.PermissionDeniedas as err:
                error_reporting_client.report_exception()
                return str(err), err.code

            gcp_logger.log_text('POST {1}/gsakey secret {0} version added'.format(add_secret_ver_result.name, app_name))

        result = json.loads(gsa_key)
        if find_secret_result:
            result['found_secret'] = find_secret_result.name
        if is_create_secret and create_secret_result:
            result['created_secret'] = create_secret_result.name
        if add_secret_ver_result:
            result['added_secret_version'] = add_secret_ver_result.name

    return jsonify(result)


@app.route('/gsakey', methods=['DELETE'])
def delete_gsa_keys():
    """Delete GSA keys passed in the request form data as a list"""
    tracer = app.config['TRACER']
    with tracer.span(name=('%s-delete' % app_name)) as span_method:
        form_key = 'gsa-key-names'
        if form_key not in request.form or not request.form[form_key]:
            return 'Missing form-data of key: {0} or value empty'.format(form_key), 400

        full_sa_key_names = request.form[form_key].split(',')
        keys_deleted = []

        for full_sa_key_name in full_sa_key_names:
            service = googleapiclient.discovery.build('iam', 'v1')
            full_sa_key_name = full_sa_key_name.strip()
            try:
                service.projects().serviceAccounts().keys().delete(name=full_sa_key_name).execute()
            except googleapiclient.errors.HttpError as err:
                err_result = json.loads(err.content.decode("utf-8"))
                err_result['deleted'] = keys_deleted
                return err_result, err.resp.status
            except BaseException as baseEx:
                error_reporting_client.report_exception()
                return {
                           'Error': str(baseEx),
                           'Info': keys_deleted
                       }, 500

            keys_deleted.append(full_sa_key_name)

        gcp_logger.log_text('DELETE {1}/gsakey {0}'.format(keys_deleted, app_name))
    return {'deleted': keys_deleted}


@app.route('/gsakey/<gsa>', methods=['GET'])
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
    with tracer.span(name=('%s-get' % app_name)) as span_method:
        # form_key = 'gsa'
        # if form_key not in request.form or not request.form[form_key]:
        #     return 'Missing form-data of key: {0} or value empty'.format(form_key), 400

        service_account_to_get = gsa
        service = googleapiclient.discovery.build('iam', 'v1')

        keys = service.projects().serviceAccounts().keys().list(
            name='projects/-/serviceAccounts/' + service_account_to_get).execute()
        gcp_logger.log_text('GET {1}/gsakey {0}'.format(service_account_to_get, app_name))

    return jsonify(keys)


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
