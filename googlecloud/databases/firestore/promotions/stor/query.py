#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/
# reference https://cloud.google.com/firestore/docs/samples

import os
import re
from datetime import datetime
from http import HTTPStatus

from flask import Blueprint
from flask import jsonify
from flask import request
from google.cloud import firestore
from google.cloud import logging
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

#     DEFAULT = 0
#     DEBUG = 100
#     INFO = 200
#     NOTICE = 300
#     WARNING = 400
#     ERROR = 500
#     CRITICAL = 600
#     ALERT = 700
#     EMERGENCY = 800
LOG_SEVERITY_DEFAULT = 'DEFAULT'
LOG_SEVERITY_INFO = 'INFO'
LOG_SEVERITY_WARNING = 'WARNING'
LOG_SEVERITY_DEBUG = 'DEBUG'
LOG_SEVERITY_NOTICE = 'NOTICE'
LOG_SEVERITY_ERROR = 'ERROR'

query_api = Blueprint('query_api', __name__)
firestore_path = os.environ['FIRESTORE_PATH']
firestore_paths = firestore_path.split('/')
BASE_COLL = firestore_paths[0]
PROMO_DOC = firestore_paths[1]
PROMO_COLL = firestore_paths[2]
app_name = PROMO_DOC
doc_field_redemption = 'redemption'


def log(text, severity=LOG_SEVERITY_DEFAULT, log_name=app_name):
    logging_client = logging.Client(project=os.environ['PROJECT_ID'])
    logger = logging_client.logger(log_name)

    return logger.log_text(text, severity=severity)


try:
    import googleclouddebugger

    googleclouddebugger.enable(
        module='firestor-operation',
        version=os.environ.get("VERSION", str(datetime.now())),
        breakpoint_enable_canary=True,
        service_account_json_file=os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '/opt/cdbg/gcp-svc.json'))
except ImportError as err:
    log(text="import googleclouddebugger failed: {0}".format(str(err)), severity=LOG_SEVERITY_ERROR)
    pass

tracer_provider = TracerProvider()
cloud_trace_exporter = CloudTraceSpanExporter()
tracer_provider.add_span_processor(
    # BatchSpanProcessor buffers spans and sends them in batches in a
    # background thread. The default parameters are sensible, but can be
    # tweaked to optimize your performance
    BatchSpanProcessor(cloud_trace_exporter)
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)


def verify_basic_auth():
    auth_key = 'BASIC_AUTH'
    auth_token = request.headers.get('Authorization')
    if os.environ.get(auth_key) and os.environ.get(auth_key) == auth_token:
        log('authenticated request by basic token', LOG_SEVERITY_DEBUG)
        return f'Authenticated', HTTPStatus.OK
    else:
        return f'Missing or wrong Authorization header! Is the flask app running with environment variable {auth_key}\'s value set to the Authorization header?', HTTPStatus.UNAUTHORIZED


@query_api.route('/{}'.format(PROMO_DOC), methods=['GET'])
def get_all_promos():
    auth_msg, auth_res = verify_basic_auth()
    if auth_res != HTTPStatus.OK:
        return auth_msg, auth_res

    with tracer.start_span("Firestore operation: get all promotions") as current_span:
        db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
        docs = db.collection(BASE_COLL).document(PROMO_DOC).collection(PROMO_COLL).stream()
        response = {}
        doc_count = 0
        for doc in docs:
            response[doc.id] = doc.to_dict()
            doc_count += 1
            log(f'getting content of doc ID {doc.id}', LOG_SEVERITY_DEBUG)

        current_span.set_attribute("retrieved promotion count", doc_count)

    return jsonify(response)


@query_api.route('/{}/<promo>'.format(PROMO_DOC), methods=['GET'])
def get_promo(promo):
    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    promo_ref = db.collection(BASE_COLL).document(PROMO_DOC).collection(PROMO_COLL).document(promo)
    if not promo_ref.get().exists:
        return "Firestore document requested does not exist", HTTPStatus.NOT_FOUND

    promo_snapshot = promo_ref.get().to_dict()

    return jsonify(promo_snapshot), HTTPStatus.OK


@query_api.route('/{}/unused'.format(PROMO_DOC), methods=['GET'])
def get_unused_promo():
    auth_msg, auth_res = verify_basic_auth()
    if auth_res != HTTPStatus.OK:
        return auth_msg, auth_res

    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    promo_ref = db.collection(BASE_COLL).document(PROMO_DOC).collection(PROMO_COLL)
    docs = promo_ref.where(doc_field_redemption, u'==', None).stream()
    response = {}
    for doc in docs:
        response[doc.id] = doc.to_dict()
        log(f'getting content of doc ID {doc.id}', LOG_SEVERITY_DEBUG)

    return jsonify(response)


def is_email_valid(email):
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if re.fullmatch(regex, email):
        return True
    else:
        return False


@query_api.route('/{}'.format(PROMO_DOC), methods=['POST'])
def create_promo():
    auth_msg, auth_res = verify_basic_auth()
    if auth_res != HTTPStatus.OK:
        return auth_msg, auth_res

    request_body = request.get_json()
    req_key_exp = 'expiry'
    req_key_svc = 'service-category'
    req_key_charge = 'charge'
    req_key_form = 'form-url'

    if not request_body or req_key_exp not in request_body or req_key_svc not in request_body \
            or req_key_charge not in request_body or req_key_form not in request_body:
        return f'Missing some items in request JSON body: {{"{req_key_exp}": "2025-12-31 23:59:59",' \
               f' "{req_key_svc}": "Google cloud migration", "{req_key_charge}": dollar amount,' \
               f' "{req_key_form}": "Google form url" }}', \
               HTTPStatus.BAD_REQUEST

    exp_datetime = datetime.strptime(request_body[req_key_exp], '%Y-%m-%d %H:%M:%S')
    promo_doc = {
        req_key_svc: request_body[req_key_svc],
        req_key_exp: exp_datetime,
        req_key_charge: request_body[req_key_charge],
        req_key_form: request_body[req_key_form],
        doc_field_redemption: None
    }
    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    doc = db.collection(BASE_COLL).document(PROMO_DOC).collection(PROMO_COLL).add(promo_doc)
    doc_id = doc[1].id
    log('promo Firestore doc created with ID {}'.format(doc_id), LOG_SEVERITY_INFO)

    return jsonify({
        doc_id: promo_doc
    })


@query_api.route('/{}/<promo>'.format(PROMO_DOC), methods=['PUT'])
def redeem_promo(promo):
    request_body = request.get_json()
    req_key_name = 'name'
    req_key_email = 'email'

    if not request_body or req_key_name not in request_body or req_key_email not in request_body:
        return f"Missing request body of JSON: {{'{req_key_email}': 'your@email.com', '{req_key_name}': 'First Last' }}", HTTPStatus.BAD_REQUEST

    email = request_body[req_key_email]
    if not is_email_valid(email):
        return f"email in request body is invalid: {email}", HTTPStatus.BAD_REQUEST

    with tracer.start_span("Firestore operation: redeem a promotion") as current_span:
        db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
        promo_ref = db.collection(BASE_COLL).document(PROMO_DOC).collection(PROMO_COLL).document(promo)
        if not promo_ref.get().exists:
            log('promo code {} not found during redemption'.format(promo), LOG_SEVERITY_WARNING)
            return "Firestore document requested does not exist; make sure you entered the right promo code", HTTPStatus.NOT_FOUND
        else:
            redeeming = promo_ref.get().to_dict()
            if redeeming['redemption']:
                current_span.set_attribute("is redemption successful", False)
                log('Attempted to consume redeemed promo code {0}'.format(promo))
                return "Firestore document has been redeemed; you can't redeemed a used promotion!", HTTPStatus.BAD_REQUEST
            if redeeming['expiry'] < datetime.now(redeeming['expiry'].tzinfo):
                current_span.set_attribute("is redemption successful", False)
                log('Attempted to consume expired promo code {0}'.format(promo))
                return "Firestore document has expired; you can't redeemed an expired promotion!", HTTPStatus.BAD_REQUEST
            redeeming['redeemed-by'] = f"{email}:{request_body[req_key_name]}"
            redeeming['redemption'] = datetime.utcnow()
            promo_ref.set(redeeming)
            current_span.set_attribute("is redemption successful", True)
            log('promo code {} redemption succeeded'.format(promo), LOG_SEVERITY_INFO)
            return jsonify(redeeming)


@query_api.route('/healthz'.format(PROMO_DOC), methods=['GET'])
def health_check():
    return jsonify({'status': 'OK'})
