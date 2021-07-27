#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/

from flask import Blueprint
from flask import Response
from flask import abort
from flask import jsonify
from flask import request
import os
from google.cloud import logging
from google.cloud.logging import Resource
from google.cloud import firestore

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
def get_orders():
    db = firestore.Client(project=os.environ['FIRESTORE_PROJECT_ID'])
    docs = db.collection('hil-test').document(PROMO_DOC).collection('2021').stream()
    response = []
    for doc in docs:
        response.append(doc.to_dict())
        log(f'getting content of doc ID {doc.id}', LOG_SEVERITY_DEBUG)

    return jsonify(response)
