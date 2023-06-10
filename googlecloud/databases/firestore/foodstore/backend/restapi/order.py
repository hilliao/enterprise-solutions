from google.cloud import firestore
from flask import jsonify
from flask import request
from flask import abort
from flask import Response
from restapi import CUST_TOKEN
from restapi import ORDERS_COLL
from flask import Blueprint

order_api = Blueprint('order_api', __name__)


@order_api.route('/' + ORDERS_COLL, methods=['POST'])
def post_order():
    db = firestore.Client()

    # check if customer with the token exists to allow posting orders
    customer = get_customer(db)

    if not customer:
        return Response('customer of token not found; register your account with sysadmin first', status=401)
    else:
        order_dict = request.get_json()
        order_dict[CUST_TOKEN] = request.headers[CUST_TOKEN]
        update_time, order_ref = db.collection(ORDERS_COLL).add(order_dict)
        order_snapshot = order_ref.get()

        return jsonify({
            order_snapshot.id: order_snapshot.to_dict(),
            'updated_time': str(update_time)
        })


@order_api.route('/{}/<order>'.format(ORDERS_COLL), methods=['PUT'])
def put_order(order):
    db = firestore.Client()

    # check if customer with the token exists to allow putting orders
    customer = get_customer(db)

    if not customer:
        return Response('customer of token not found; register your account with sysadmin first', status=401)
    else:
        order_dict = request.get_json()
        order_dict[CUST_TOKEN] = request.headers[CUST_TOKEN]
        order_ref = db.collection(ORDERS_COLL).document(order)
        order_ref.set(order_dict)

        return jsonify(order_dict)


def get_customer(db):
    if CUST_TOKEN not in request.headers:
        abort(Response('missing header of {}'.format(CUST_TOKEN), status=401))

    token = request.headers[CUST_TOKEN]
    cust_ref = db.collection('customers').document(token)
    cust_snapshot = cust_ref.get()

    if cust_snapshot.exists:
        return cust_snapshot.to_dict()
    else:
        return None


@order_api.route('/{}/<order>'.format(ORDERS_COLL), methods=['GET'])
def get_orders(order):
    db = firestore.Client()
    order_ref = db.collection(ORDERS_COLL).document(order)
    order_snapshot = order_ref.get()
    if not order_snapshot.exists:
        return Response('order {} not found'.format(order), status=404)

    order_dict = order_snapshot.to_dict()

    if order_dict[CUST_TOKEN] == request.headers[CUST_TOKEN]:
        order_dict.pop(CUST_TOKEN, None)
        return jsonify(order_dict)
    else:
        return Response('header {} has an invalid value'.format(CUST_TOKEN), status=405)


@order_api.route('/{}/<order>'.format(ORDERS_COLL), methods=['DELETE'])
def delete_orders(order):
    db = firestore.Client()

    # Good security practice is to check if customer with the token exists to allow deleting orders
    # bypassing such check will allow hackers to attempt deleting orders to check if such order ID exists
    customer = get_customer(db)

    if not customer:
        return Response('customer of token not found; register your account with sysadmin first', status=401)
    else:
        # verify the order has the correct customer token before deletion
        order_ref = db.collection(ORDERS_COLL).document(order)
        order_snapshot = order_ref.get()
        if not order_snapshot.exists:
            return Response('order {} not found'.format(order), status=404)

        order_dict = order_snapshot.to_dict()
        token = request.headers[CUST_TOKEN]

        # allow deleting the order if the customer token matches
        if order_dict[CUST_TOKEN] == token:
            if order_dict['state'] == 'not started':
                db.collection(ORDERS_COLL).document(order).delete()
                return jsonify({'order_deleted': order})
            else:
                return Response('order state has changed to {}'.format(order_dict['state']), status=405)
        else:
            return Response('header {} has value {} not matching order {}'.format(CUST_TOKEN, token, order), status=401)
