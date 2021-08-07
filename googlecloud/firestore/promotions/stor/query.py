#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/

import os
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


def log(text, severity=LOG_SEVERITY_DEFAULT, log_name=app_name):
    logging_client = logging.Client(project=os.environ['PROJECT_ID'])
    logger = logging_client.logger(log_name)

    return logger.log_text(text, severity=severity,
                           resource=Resource(type="cloud_run_revision",
                                             labels={'configuration_name': 'persistence-layer'}
                                             )
                           )


@query_api.route('/{}'.format(PROMO_DOC), methods=['GET'])
def get_all_promos():
    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    docs = db.collection('hil-test').document(PROMO_DOC).collection('2021').stream()
    response = []
    for doc in docs:
        response.append(doc.to_dict())
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
    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    promo_ref = db.collection('hil-test').document(PROMO_DOC).collection('2021')
    docs = promo_ref.where(u'redemption', u'==', None).stream()
    response = []
    for doc in docs:
        response.append(doc.to_dict())
        log(f'getting content of doc ID {doc.id}', LOG_SEVERITY_DEBUG)

    return jsonify(response)


@query_api.route('/{}/<promo>'.format(PROMO_DOC), methods=['PUT'])
def redeem_promo(promo):
    request_body = request.get_json()
    req_key_name = 'name'
    req_key_email = 'email'

    if not request_body or req_key_name not in request_body or req_key_email not in request_body:
        return f"Missing request body of JSON: {{'{req_key_email}': 'your@email.com', '{req_key_name}': 'First Last' }}", HTTPStatus.BAD_REQUEST

    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    promo_ref = db.collection('hil-test').document(PROMO_DOC).collection('2021').document(promo)
    if not promo_ref.get().exists:
        return "Firestore document requested does not exist; make sure you entered the right promo code", HTTPStatus.NOT_FOUND
    else:
        redeeming = promo_ref.get().to_dict()
        redeeming['redeemed-by'] = f"{request_body[req_key_email]}:{request_body[req_key_name]}"
        redeeming['redemption'] = datetime.utcnow()
        promo_ref.set(redeeming)
        return jsonify(redeeming)
