import datetime
import json
import os
from concurrent import futures
from concurrent.futures.thread import ThreadPoolExecutor
from http import HTTPStatus

import functions_framework
import requests
from flask import abort
from google.cloud import bigquery
from google.cloud import logging
from google.cloud import secretmanager
from google.cloud import storage

LOG_SEVERITY_DEFAULT = 'DEFAULT'
LOG_SEVERITY_INFO = 'INFO'
LOG_SEVERITY_WARNING = 'WARNING'
LOG_SEVERITY_DEBUG = 'DEBUG'
LOG_SEVERITY_NOTICE = 'NOTICE'
LOG_SEVERITY_ERROR = 'ERROR'
app_name = 'smart-invest'


def log(text, severity=LOG_SEVERITY_DEFAULT, log_name=app_name):
    logging_client = logging.Client(project=os.environ['PROJECT_ID'])
    logger = logging_client.logger(log_name)

    return logger.log_text(text, severity=severity)


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
            quotes = get_cached_quotes(bucket, list_tickers)

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
        url = "https://yh-finance.p.rapidapi.com/market/v2/get-quotes"
        tickers = http_request.args.get('tickers')  # GOOGL,IVV
        if not tickers:
            return "missing query string tickers", HTTPStatus.BAD_REQUEST

        querystring = {"region": "US",
                       "symbols": tickers}  # "QQQ,ONEQ,IVV,VOO,JETS,VHT,VDE,VFH,VTWO,BRK-B,ACN,AMD,GOOGL,AMZN,MSFT,MRVL,FB,QCOM,CRM,SNAP,TSM,BHP,RIO,EXPE,BKNG,HD"

        env_var_secret_name = 'SECRET_NAME_YH_API_KEY'
        YH_API_key = get_secret_value(env_var_secret_name)

        headers = {
            "X-RapidAPI-Host": "yh-finance.p.rapidapi.com",
            "X-RapidAPI-Key": YH_API_key
        }

        response = requests.request("GET", url, headers=headers, params=querystring)
        storage_client = storage.Client()
        bucket = storage_client.get_bucket('test-vpc-341000')

        counter = 0
        saved_quotes = {}

        for tickers in querystring['symbols'].split(','):
            gcs_file = bucket.blob('{0}/{1}.json'.format(os.environ.get('FOLDER'), tickers))
            raw_str = str(response.json()['quoteResponse']['result'][counter])
            replaced_str = raw_str.replace("'", '"').replace('True', 'true').replace('False', 'false')
            gcs_file.upload_from_string(replaced_str)
            saved_quotes[tickers] = gcs_file.media_link
            counter += 1

        return saved_quotes

    elif http_request.method == 'DELETE':
        return abort(403)
    else:
        return abort(404)


def get_secret_value(env_var_secret_name):
    sm_client = secretmanager.SecretManagerServiceClient()
    secret_path_latest = sm_client.secret_path(os.environ.get('SECRET_MANAGER_PROJECT_ID'),
                                               os.environ.get(env_var_secret_name)) + "/versions/latest"
    # TODO: check if the secret exists
    secret_latest_version = sm_client.access_secret_version(request={"name": secret_path_latest})
    log('read secret value for secret name {}'.format(os.environ.get(env_var_secret_name)), LOG_SEVERITY_NOTICE)
    secret_value = secret_latest_version.payload.data.decode("UTF-8")
    return secret_value


def serialize_exceptions(dict_some_val_ex):
    if all(isinstance(quote, Exception) for quote in dict_some_val_ex.values()):
        dict_some_val_ex = {k: str(v) for (k, v) in dict_some_val_ex.items()}
        return dict_some_val_ex, HTTPStatus.GONE
    if any(isinstance(quote, Exception) for quote in dict_some_val_ex.values()):
        dict_some_val_ex = {k: (str(v) if isinstance(v, Exception) else v) for (k, v) in dict_some_val_ex.items()}
        return dict_some_val_ex, HTTPStatus.MULTI_STATUS
    else:
        return dict_some_val_ex


access_token = None
trade_station_url = 'https://api.tradestation.com/v3'
trade_station_market_data = '/marketdata/stream/quotes/{symbols}'
trade_station_token_url = "https://signin.tradestation.com/oauth/token"


def get_cached_quote(bucket, ticker):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket)
    blob = bucket.blob("{0}/{1}.json".format(os.environ.get('FOLDER'), ticker))
    try:
        json_str = blob.download_as_string().decode()
        json_quote = json.loads(json_str)
    except Exception as err:
        log(text='Reading quote of {} from Google cloud storage failed: {}'.format(ticker, str(err)),
            severity=LOG_SEVERITY_WARNING)
        return err
    # attempt to call Trade Station API to get real time price quote
    global access_token
    if not access_token:
        # TODO: check if secret exists and is in the correct , separated format
        client_id_secret = get_secret_value('SECRET_NAME_CLIENT_ID_SECRET')
        client_id = client_id_secret.split(',')[0]
        client_secret = client_id_secret.split(',')[1]
        refresh_token = get_secret_value('SECRET_NAME_REFRESH_TOKEN')
        payload = 'grant_type=refresh_token&client_id={}&client_secret={}&refresh_token={}'.format(
            client_id, client_secret, refresh_token
        )
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

        token_response = requests.request("POST", trade_station_token_url, headers=headers, data=payload)
        if token_response.status_code == HTTPStatus.OK:
            access_token = token_response.json()['access_token']

    trade_station_quote = '{}{}'.format(trade_station_url, trade_station_market_data.format(symbols=ticker))
    headers = {
        'Authorization': 'Bearer {}'.format(access_token)
    }
    with requests.request("GET", trade_station_quote, headers=headers, stream=True) as quote_response:
        if quote_response.status_code == HTTPStatus.OK:
            for chunk in quote_response.iter_content(1024 * 10, decode_unicode=True):
                ts_quote = json.loads(chunk)
                break

            json_quote.update(ts_quote)
        else:
            log(text='TradeStation get quote of {} failed'.format(ticker), severity=LOG_SEVERITY_WARNING)

    return json_quote


MAX_WORKERS = 10


def get_cached_quotes(bucket, tickers):
    thread_results = {}
    with ThreadPoolExecutor(max_workers=int(MAX_WORKERS)) as executor:
        for ticker in tickers:
            thread_results[ticker] = executor.submit(get_cached_quote, bucket, ticker)

        futures.wait(thread_results.values(), return_when=futures.ALL_COMPLETED)

    for ticker in thread_results:
        # exception thrown from .result() method if any exception happened
        try:
            thread_results[ticker] = thread_results[ticker].result()
        except Exception as ex:
            thread_results[ticker] = ex

    return thread_results


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
                bucket = os.environ.get('BUCKET')

                if orders and type(orders) is dict:
                    list_tickers = orders.keys()
                    quotes = get_cached_quotes(bucket, list_tickers)
                    trades = {}
                    total = 0
                    for ticker in quotes:
                        if isinstance(quotes[ticker], Exception):
                            # assign the Exception to the dictionary's value for later processing
                            trades[ticker] = quotes[ticker]
                            continue
                        cash = int(orders[ticker])
                        amplify = request_json['amplify']
                        bq_table = request_json['bq_table']
                        fiftyDayAverage = quotes[ticker]['fiftyDayAverage']
                        twoHundredDayAverage = quotes[ticker]['twoHundredDayAverage']
                        if quotes[ticker]['Last']:
                            ticker_price = float(quotes[ticker]['Last'])
                        else:
                            ticker_price = quotes[ticker]['regularMarketPrice']

                        # average of the moving averages minus the current stock price
                        average_price_diff = ((fiftyDayAverage + twoHundredDayAverage) / 2 - ticker_price)
                        # how much more or less does the trader want to buy
                        buy_adjust = average_price_diff / ticker_price
                        # how much cash does thr trader want to use
                        adjusted_cash = (buy_adjust + 1) * cash
                        # how many shares to buy
                        buy_share_count = adjusted_cash / ticker_price
                        # 2 decimals at mast
                        shares_count = round(max(buy_share_count * amplify, 0), 2)
                        trades[ticker] = {"shares": shares_count,
                                          "cash": shares_count * ticker_price,
                                          "price": ticker_price}
                        total += trades[ticker]["cash"]

                    # save to a BigQuery table
                    # TODO: fix the hard coded account number
                    account_num = -1
                    recommended_timestamp = str(datetime.datetime.utcnow())
                    rows_to_insert = []
                    for ticker, order in trades.items():
                        if isinstance(order, Exception):
                            continue
                        rows_to_insert.append(
                            {"account": account_num,
                             "ticker": ticker,
                             "cash": order["cash"],
                             "price": order["price"],
                             "shares": order["shares"],
                             "updated": recommended_timestamp}
                        )
                    client = bigquery.Client()
                    try:
                        errors = client.insert_rows_json(bq_table, rows_to_insert)
                        if errors:
                            log("Encountered errors while inserting rows to BigQuery table "
                                "{}: {}".format(bq_table, errors),
                                severity=LOG_SEVERITY_ERROR)
                    except Exception as ex:
                        log("Encountered errors while inserting rows to BigQuery table "
                            "{}: {}".format(bq_table, ex),
                            severity=LOG_SEVERITY_ERROR)

                    serialized_trades = serialize_exceptions(trades)
                    # returned a tuple if there are exceptions in the values
                    if type(serialized_trades) is tuple:
                        return {"trades": serialized_trades[0], "total": total}, serialized_trades[1]
                    else:
                        return {"trades": serialized_trades, "total": total}
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
        # TODO: check if secret exists and is in the correct , separated format
        client_id_secret = get_secret_value('SECRET_NAME_CLIENT_ID_SECRET')
        client_id = client_id_secret.split(',')[0]
        client_secret = client_id_secret.split(',')[1]
        payload = 'grant_type=authorization_code&client_id={}&client_secret={}&code={}&redirect_uri={}' \
            .format(client_id, client_secret, authorization_code,
                    # TODO: change to self url
                    'https://get-authorization-code-slnskhfzsa-uw.a.run.app')
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

        tokens = requests.request("POST", trade_station_token_url, headers=headers, data=payload)

        return {
            'authorization_code': authorization_code,
            'state': state,
            'tokens': tokens.json()
        }
    else:
        return abort(403)
