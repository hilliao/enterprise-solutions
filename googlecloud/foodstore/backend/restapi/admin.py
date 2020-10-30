from flask import Blueprint
from flask import Response
from flask import abort
from flask import jsonify
from flask import request
from google.cloud import firestore

from restapi import ADMIN_TOKEN, ADMIN_TOKEN_VALUE, CUSTOMERS_COLL

admin_api = Blueprint('admin_api', __name__)


def authenticate_admin():
    if ADMIN_TOKEN not in request.headers:
        abort(Response('missing header of {}'.format(ADMIN_TOKEN), status=401))

    token = request.headers[ADMIN_TOKEN]

    if token != ADMIN_TOKEN_VALUE:
        abort(Response('header {} has an invalid value'.format(ADMIN_TOKEN)))


@admin_api.route('/{}/<customer_token>'.format(CUSTOMERS_COLL), methods=['PUT'])
def put_customer(customer_token):
    db = firestore.Client()
    authenticate_admin()
    customer_dict = request.get_json()

    cust_ref = db.collection(CUSTOMERS_COLL).document(customer_token)
    cust_ref.set(customer_dict)

    return jsonify(customer_dict)


@admin_api.route('/{}'.format(CUSTOMERS_COLL), methods=['POST'])
def post_customer():
    db = firestore.Client()
    authenticate_admin()
    customer_dict = request.get_json()

    update_time, cust_ref = db.collection(CUSTOMERS_COLL).add(customer_dict)
    cust_snapshot = cust_ref.get()

    return jsonify({
        cust_snapshot.id: cust_snapshot.to_dict(),
        'updated_time': str(update_time)
    })
