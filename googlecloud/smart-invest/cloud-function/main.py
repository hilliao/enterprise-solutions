import json
import os
from http import HTTPStatus

import functions_framework
import requests
from flask import abort
from google.cloud import storage
from cloud_native import get_secret_value

import algo_trade
import brokerage
import cloud_native


# see exported postman .json file for how to invoke.
@functions_framework.http
def stock_quotes(http_request):
    # read stock quotes
    if http_request.method == 'GET':
        gs_uri = http_request.args.get('gs_uri')  # gs://test-vpc-341000/mock/quotes.json
        tickers = http_request.args.get('tickers')  # GOOGL,IVV
        bucket = os.environ.get('BUCKET')

        if tickers:
            list_tickers = tickers.split(',')
            quotes = brokerage.get_cached_or_realtime_quotes(bucket, list_tickers)

            quotes_ex_serialized = serialize_exceptions(quotes)
            return quotes_ex_serialized

        elif gs_uri:
            bucket = gs_uri.split('/')[2]
            object_name = "/".join(gs_uri.split("/")[3:])
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket)
            blob = bucket.blob(object_name)
            json_str = blob.download_as_string().decode()

            return json.loads(json_str)
        else:
            return "missing query string tickers or gs_uri", HTTPStatus.BAD_REQUEST

    # save the quotes from Yahoo finance to Google cloud storage for get quotes to read from the bucket
    elif http_request.method == 'POST':
        tickers = http_request.args.get('tickers')  # GOOGL,IVV
        if not tickers:
            return "missing query string tickers", HTTPStatus.BAD_REQUEST

        yh_finance_res = brokerage.yh_finance_get_quotes(tickers)
        storage_client = storage.Client()
        bucket = storage_client.bucket(os.environ.get('BUCKET'))
        quote_response = yh_finance_res.json()['quoteResponse']['result']

        saved_quotes = {}
        for yh_quote in quote_response:
            ticker = yh_quote['symbol']
            gcs_file = bucket.blob('{0}/{1}.json'.format(os.environ.get('FOLDER'), ticker))
            raw_str = str(yh_quote)
            # Yahoo finance returns single quotes, upper cases in certain contents
            replaced_str = raw_str.replace("'", '"').replace('True', 'true').replace('False', 'false')
            gcs_file.upload_from_string(replaced_str)
            saved_quotes[ticker] = gcs_file.media_link

        return saved_quotes

    elif http_request.method == 'DELETE':
        return abort(403)
    else:
        return abort(404)


def serialize_exceptions(dict_maybe_some_val_ex):
    # every value is an exception
    if all(isinstance(quote, Exception) for quote in dict_maybe_some_val_ex.values()):
        http_status = HTTPStatus.GONE
    # some values are exceptions
    elif any(isinstance(quote, Exception) for quote in dict_maybe_some_val_ex.values()):
        http_status = HTTPStatus.MULTI_STATUS
    # no exception in values
    else:
        http_status = HTTPStatus.OK

    # serialize per value's type
    for k in dict_maybe_some_val_ex:
        if isinstance(dict_maybe_some_val_ex[k], Exception):
            dict_maybe_some_val_ex[k] = str(dict_maybe_some_val_ex[k])
        elif isinstance(dict_maybe_some_val_ex[k], brokerage.Quote):
            dict_maybe_some_val_ex[k] = dict_maybe_some_val_ex[k].raw_dict
        elif isinstance(dict_maybe_some_val_ex[k], algo_trade.Order):
            dict_maybe_some_val_ex[k] = dict_maybe_some_val_ex[k].to_dict()

    return dict_maybe_some_val_ex, http_status


class TradeOrder:
    keys = ['intended_allocation', 'amplify', 'bq_table']

    def __init__(self, order_body: dict):
        if not all(item in order_body for item in self.keys):
            raise Exception("Malformed order request body dict does not have keys: {}".format(self.keys))

        # 1.1 means buy 10% more shares
        if 'amplify' in order_body and isinstance(order_body['amplify'], float):
            self.amplify = order_body['amplify']
        else:
            raise Exception("order request body dictionary key amplify does not have value of type float")

        # project_id.dataset.table for recording trade recommendations
        if 'bq_table' in order_body and isinstance(order_body['bq_table'], str):
            self.bq_table = order_body['bq_table']
        else:
            raise Exception("order request body dictionary key bq_table does not have value of type str")

        # {GOOGL: 5000,IVV: 12000}
        if 'intended_allocation' in order_body and isinstance(order_body['intended_allocation'], dict):
            self.intended_allocation = order_body['intended_allocation']
        else:
            raise Exception("order request body dictionary key intended_allocation does not have value of type dict")

        # check key is ticker string, value is float for allocation cash amount
        for k, v in self.intended_allocation.items():
            if not isinstance(k, str):
                raise Exception("request body intended_allocation dictionary does not have key of type str")
            if not (isinstance(v, float) or isinstance(v, int)):
                raise Exception("request body intended_allocation dictionary does not have value of type float or int")

        # accept optional account number. Trade station's account number is of type str
        if 'account' in order_body:
            self.account = str(order_body['account'])
            # Expand TimeInForce.duration parameter at https://api.tradestation.com/docs/specification/#operation/PlaceOrder
            # to see available enumerations
            if 'duration' in order_body and isinstance(order_body['duration'], str):
                self.duration = order_body['duration']
            else:
                raise Exception("request body dictionary key account is given but not duration of type str")

            # limit_order_off parameter which sets the buy limit order's price off from the current price
            if 'limit_order_off' in order_body and isinstance(order_body['limit_order_off'], float):
                self.limit_order_off = order_body['limit_order_off']
            else:
                raise Exception("request body dictionary key account is given but not limit_order_off of type float")
        else:
            self.account = None


# see exported postman .json file for how to invoke.
# if the account number isn't in the request body, don't execute trades but provide trade recommendations.
@functions_framework.http
def execute_trade(http_request):
    if http_request.method == 'POST':
        if 'content-type' in http_request.headers and http_request.headers['content-type'] == 'application/json':
            request_json = http_request.get_json(silent=True)
            if request_json:
                try:
                    trade_order = TradeOrder(request_json)
                except Exception as ex:
                    return "Exception type {} => {}".format(type(ex), str(ex)), HTTPStatus.BAD_REQUEST
                bucket = os.environ.get('BUCKET')
                list_tickers = trade_order.intended_allocation
                quotes = brokerage.get_cached_or_realtime_quotes(bucket, list_tickers)

                # returned dict may have values of type Exception where recommendations failed
                trades = algo_trade.recommend(trade_order.amplify, trade_order.intended_allocation, quotes)
                sum_cash = 0
                [sum_cash := sum_cash + order.cash for order in trades.values() if not isinstance(order, Exception)]

                # save to a BigQuery table
                if trade_order.account:
                    errors = cloud_native.insert_to_bq(trade_order.bq_table, trades, int(trade_order.account))
                else:
                    errors = cloud_native.insert_to_bq(trade_order.bq_table, trades)

                cloud_native.log(text='Inserting to BigQuery has errors: {}'.format(errors),
                                 severity=cloud_native.LOG_SEVERITY_DEBUG)

                # execute trades if trade station account number is provided
                if trade_order.account:
                    if trade_order.limit_order_off:
                        brokerage.execute_trade_order(trades,
                                                      trade_order.account,
                                                      duration=trade_order.duration,
                                                      limit_order_off=float(trade_order.limit_order_off))
                    else:
                        brokerage.execute_trade_order(trades, trade_order.account)

                serialized_trades = serialize_exceptions(trades)
                # returned tuple's 2nd item is the HTTPStatus code
                return {"trades": serialized_trades[0], "sum_cash": sum_cash}, serialized_trades[1]
            else:
                return "Request body JSON is Null", HTTPStatus.BAD_REQUEST
        else:
            return "content_type != 'application/json", HTTPStatus.BAD_REQUEST
    else:
        return abort(404)



# doc: https://api.tradestation.com/docs/fundamentals/authentication/auth-code/
@functions_framework.http
def get_authorization_code(http_request):
    if http_request.method == 'GET':
        authorization_code = http_request.args.get('code')
        account_number = http_request.args.get('state')
        redirect_uri = http_request.base_url

        # get client id and client secret from Google secret manager
        TradeStation_OAuth0 = get_secret_value('SECRET_NAME_TradeStation_OAuth0')
        TradeStation_OAuth0_dict = json.loads(TradeStation_OAuth0)

        client_id = TradeStation_OAuth0_dict[account_number]['client_id']
        client_secret = TradeStation_OAuth0_dict[account_number]['client_secret']
        payload = 'grant_type=authorization_code&client_id={}&client_secret={}&code={}&redirect_uri={}'.format(
            client_id, client_secret, authorization_code, redirect_uri)
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

        tokens = requests.request("POST", brokerage.trade_station_token_url, headers=headers, data=payload)

        return {
            'authorization_code': authorization_code,
            'state': account_number,
            'tokens': tokens.json()
        }
    else:
        return abort(403)
