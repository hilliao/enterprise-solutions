import json
import os
from http import HTTPStatus

import functions_framework
import requests
from flask import abort
from google.cloud import storage

import algo_trade
import brokerage
import cloud_native


# https://stock-quotes-slnskhfzsa-uw.a.run.app/?tickers=GOOGL,IVV,AMZN
# curl -X POST http://127.0.0.1:8080/?tickers=AAPL,TSLA -i
# http://127.0.0.1:8080/?tickers=AMD,GOOGL,UBER
@functions_framework.http
def stock_quotes(http_request):
    # read stock quotes
    if http_request.method == 'GET':
        gs_uri = http_request.args.get('gs_uri')  # gs://test-vpc-341000/mock/quotes.json
        tickers = http_request.args.get('tickers')  # GOOGL,IVV
        bucket = os.environ.get('BUCKET')

        if tickers:
            list_tickers = tickers.split(',')
            quotes = brokerage.get_cached_quotes(bucket, list_tickers)

            return serialize_exceptions(quotes)

        elif gs_uri:
            bucket = gs_uri.split('/')[2]
            object_name = "/".join(gs_uri.split("/")[3:])
            storage_client = storage.Client()
            bucket = storage_client.get_bucket(bucket)
            blob = bucket.blob(object_name)

            json_str = blob.download_as_string().decode()
            quotes = json.loads(json_str)

        else:
            return "missing query string tickers or gs_uri", HTTPStatus.BAD_REQUEST

        return quotes

    # save the quotes from Yahoo finance to Google cloud storage for get quotes to read from the bucket
    elif http_request.method == 'POST':
        tickers = http_request.args.get('tickers')  # GOOGL,IVV
        if not tickers:
            return "missing query string tickers", HTTPStatus.BAD_REQUEST

        yh_finance_res = brokerage.yh_finance_get_quotes(tickers)
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(os.environ.get('BUCKET'))

        counter = 0
        saved_quotes = {}

        for ticker in tickers.split(','):
            gcs_file = bucket.blob('{0}/{1}.json'.format(os.environ.get('FOLDER'), ticker))
            raw_str = str(yh_finance_res.json()['quoteResponse']['result'][counter])
            # Yahoo finance returns single quotes, upper cases in certain contents
            replaced_str = raw_str.replace("'", '"').replace('True', 'true').replace('False', 'false')
            gcs_file.upload_from_string(replaced_str)
            saved_quotes[ticker] = gcs_file.media_link
            counter += 1

        return saved_quotes

    elif http_request.method == 'DELETE':
        return abort(403)
    else:
        return abort(404)


def serialize_exceptions(dict_some_val_ex):
    if all(isinstance(quote, Exception) for quote in dict_some_val_ex.values()):
        dict_some_val_ex = {k: str(v) for (k, v) in dict_some_val_ex.items()}
        return dict_some_val_ex, HTTPStatus.GONE
    if any(isinstance(quote, Exception) for quote in dict_some_val_ex.values()):
        dict_some_val_ex = {k: (str(v) if isinstance(v, Exception) else v) for (k, v) in dict_some_val_ex.items()}
        return dict_some_val_ex, HTTPStatus.MULTI_STATUS
    else:
        return dict_some_val_ex


# curl -X POST https://trade-recommendation-slnskhfzsa-uw.a.run.app -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"orders": {"GOOGL": 5000,"QQQ": 15000,"DAL": 800},"amplify": 1,"bq_table": "test-vpc-341000.datalake.recommended_trades"}' -i
# curl -X POST http://localhost:8080 -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"orders": {"GOOGL": 5000,"QQQ": 15000,"DAL": 800},"amplify": 1,"bq_table": "test-vpc-341000.datalake.recommended_trades"}' -i
@functions_framework.http
def trade_recommendation(http_request):
    if http_request.method == 'POST':
        if 'content-type' in http_request.headers and http_request.headers['content-type'] == 'application/json':
            request_json = http_request.get_json(silent=True)
            header_params = ['orders', 'amplify', 'bq_table']
            if request_json and all(item in request_json for item in header_params):
                orders = request_json['orders']  # GOOGL: 5000,IVV: 12000
                amplify = request_json['amplify']  # 1.1
                bq_table = request_json['bq_table']  # project_id.dataset.table
                bucket = os.environ.get('BUCKET')

                if orders and type(orders) is dict:
                    list_tickers = orders.keys()
                    quotes = brokerage.get_cached_quotes(bucket, list_tickers)
                    trades = algo_trade.recommend(amplify, orders, quotes)
                    sum_cash = 0
                    [sum_cash := sum_cash + trade['cash'] for trade in trades.values() if
                     not isinstance(trade, Exception)]

                    # save to a BigQuery table
                    if 'account' in request_json:
                        errors = cloud_native.insert_to_bq(bq_table, trades, int(request_json['account']))
                    else:
                        errors = cloud_native.insert_to_bq(bq_table, trades)

                    cloud_native.log(text='Inserting to BigQuery has errors: {}'.format(errors),
                                     severity=cloud_native.LOG_SEVERITY_DEBUG)

                    # execute trades if trade station account number is provided
                    if 'account' in request_json:
                        brokerage.execute_trade_order(trades, request_json['account'])

                    serialized_trades = serialize_exceptions(trades)
                    # returned a tuple if there are exceptions in the values where exception is the 2nd item
                    if type(serialized_trades) is tuple:
                        return {"trades": serialized_trades[0], "sum_cash": sum_cash}, serialized_trades[1]
                    else:
                        return {"trades": serialized_trades, "sum_cash": sum_cash}
                else:
                    return "missing orders dictionary in request body; e,g, orders: {GOOGL: 3000, QQQ: 5000}", HTTPStatus.BAD_REQUEST
            else:
                return "JSON is invalid, or missing headers of {0}".format(header_params), HTTPStatus.BAD_REQUEST
        else:
            return "content_type != 'application/json", HTTPStatus.BAD_REQUEST
    else:
        return abort(404)


# curl "http://cloud-func-url?code=test_auth_code&state=test_state_value"
@functions_framework.http
def get_authorization_code(http_request):
    if http_request.method == 'GET':
        # get authorization code redirected 302 from https://api.tradestation.com/docs/fundamentals/authentication/auth-code/
        authorization_code = http_request.args.get(
            'code')
        state = http_request.args.get(
            'state')

        # get access and refresh token
        # TODO: check if secret exists and is in the correct comma separated format
        client_id_secret = brokerage.get_secret_value('SECRET_NAME_CLIENT_ID_SECRET')
        client_id = client_id_secret.split(',')[0]
        client_secret = client_id_secret.split(',')[1]
        payload = 'grant_type=authorization_code&client_id={}&client_secret={}&code={}&redirect_uri={}' \
            .format(client_id, client_secret, authorization_code,
                    # TODO: change to self url
                    'https://get-authorization-code-slnskhfzsa-uw.a.run.app')
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

        tokens = requests.request("POST", brokerage.trade_station_token_url, headers=headers, data=payload)

        return {
            'authorization_code': authorization_code,
            'state': state,
            'tokens': tokens.json()
        }
    else:
        return abort(403)
