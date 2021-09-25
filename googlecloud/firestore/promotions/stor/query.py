#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/
# reference https://cloud.google.com/firestore/docs/samples

import os
import re
from datetime import datetime
from http import HTTPStatus
from flask import request
from flask import Blueprint
from flask import jsonify
from google.cloud import firestore
from google.cloud import logging
from google.cloud.logging import Resource

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
PROMO_DOC = 'promotions'
app_name = PROMO_DOC
doc_field_redemption = 'redemption'


def log(text, severity=LOG_SEVERITY_DEFAULT, log_name=app_name):
    logging_client = logging.Client(project=os.environ['PROJECT_ID'])
    logger = logging_client.logger(log_name)

    return logger.log_text(text, severity=severity,
                           resource=Resource(type="cloud_run_revision",
                                             labels={'configuration_name': 'persistence-layer'}
                                             )
                           )


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

    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    docs = db.collection('hil-test').document(PROMO_DOC).collection('2021').stream()
    response = {}
    for doc in docs:
        response[doc.id] = doc.to_dict()
        log(f'getting content of doc ID {doc.id}', LOG_SEVERITY_DEBUG)

    return jsonify(response)


@query_api.route('/{}/<promo>'.format(PROMO_DOC), methods=['GET'])
def get_promo(promo):
    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    promo_ref = db.collection('hil-test').document(PROMO_DOC).collection('2021').document(promo)
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
    promo_ref = db.collection('hil-test').document(PROMO_DOC).collection('2021')
    docs = promo_ref.where(doc_field_redemption, u'==', None).stream()
    response = {}
    for doc in docs:
        response[doc.id] = doc.to_dict()
        log(f'getting content of doc ID {doc.id}', LOG_SEVERITY_DEBUG)

    return jsonify(response)


def is_email_valid(email):
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if (re.fullmatch(regex, email)):
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

    if not request_body or req_key_exp not in request_body or req_key_svc not in request_body\
            or req_key_charge not in request_body or req_key_form not in request_body:
        return f'Missing some items in request JSON body: {{"{req_key_exp}": "2025-12-31 23:59:59",' \
               f' "{req_key_svc}": "Google cloud migration", "{req_key_charge}": dollar amount,' \
               f' "{req_key_form}": "Google form url" }}',\
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
    doc = db.collection('hil-test').document(PROMO_DOC).collection('2021').add(promo_doc)
    doc_id = doc[1].id

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

    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    promo_ref = db.collection('hil-test').document(PROMO_DOC).collection('2021').document(promo)
    if not promo_ref.get().exists:
        return "Firestore document requested does not exist; make sure you entered the right promo code", HTTPStatus.NOT_FOUND
    else:
        redeeming = promo_ref.get().to_dict()
        if redeeming['redemption']:
            return "Firestore document has been redeemed; you can't redeemed an used promotion!", HTTPStatus.BAD_REQUEST
        redeeming['redeemed-by'] = f"{email}:{request_body[req_key_name]}"
        redeeming['redemption'] = datetime.utcnow()
        promo_ref.set(redeeming)
        return jsonify(redeeming)
