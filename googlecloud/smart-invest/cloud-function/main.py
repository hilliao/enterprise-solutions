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
        sm_client = secretmanager.SecretManagerServiceClient()
        secret_path_latest = sm_client.secret_path(os.environ.get('SECRET_MANAGER_PROJECT_ID'),
                                                   os.environ.get('SECRET_NAME_YH_API_KEY')) + "/versions/latest"
        # TODO: check if the secret exists
        secret_latest_ver_YH_API_key = sm_client.access_secret_version(request={"name": secret_path_latest})
        log('read from secret for Yahoo Finance API key', LOG_SEVERITY_NOTICE)
        YH_API_key = secret_latest_ver_YH_API_key.payload.data.decode("UTF-8")

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


def serialize_exceptions(dict_some_val_ex):
    if all(isinstance(quote, Exception) for quote in dict_some_val_ex.values()):
        dict_some_val_ex = {k: str(v) for (k, v) in dict_some_val_ex.items()}
        return dict_some_val_ex, HTTPStatus.GONE
    if any(isinstance(quote, Exception) for quote in dict_some_val_ex.values()):
        dict_some_val_ex = {k: (str(v) if isinstance(v, Exception) else v) for (k, v) in dict_some_val_ex.items()}
        return dict_some_val_ex, HTTPStatus.MULTI_STATUS
    else:
        return dict_some_val_ex


def get_cached_quote(bucket, ticker):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket)
    blob = bucket.blob("{0}/{1}.json".format(os.environ.get('FOLDER'), ticker))
    try:
        json_str = blob.download_as_string().decode()
    except Exception as err:
        return err
    json_quote = json.loads(json_str)
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


# curl -X PUT https://trade-recommendation-slnskhfzsa-uw.a.run.app/?tickers=IVV,GOOGL,FB -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"cash":11111, "amplify": 1}' -i
# curl -X PUT http://localhost:8080/?tickers=IVV,GOOGL,FB -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"cash":11111, "amplify": 1}' -i
@functions_framework.http
def trade_recommendation(http_request):
    if http_request.method == 'POST':
        if 'content-type' in http_request.headers and http_request.headers['content-type'] == 'application/json':
            request_json = http_request.get_json(silent=True)
            header_params = ['cash', 'amplify', 'bq_table']
            if request_json and all(item in request_json for item in header_params):
                tickers = http_request.args.get('tickers')  # GOOGL,IVV
                bucket = os.environ.get('BUCKET')

                if tickers:
                    list_tickers = tickers.split(',')
                    quotes = get_cached_quotes(bucket, list_tickers)
                    trades = {}
                    for ticker in quotes:
                        if isinstance(quotes[ticker], Exception):
                            trades[ticker] = quotes[ticker]
                            continue
                        cash = int(request_json['cash']) / len(list_tickers)
                        amplify = request_json['amplify']
                        bq_table = request_json['bq_table']
                        fiftyDayAverage = quotes[ticker]['fiftyDayAverage']
                        twoHundredDayAverage = quotes[ticker]['twoHundredDayAverage']
                        regularMarketPrice = quotes[ticker]['regularMarketPrice']

                        # average of the moving averages minus the current stock price
                        average_price_diff = ((fiftyDayAverage + twoHundredDayAverage) / 2 - regularMarketPrice)
                        # how much more or less does the trader want to buy
                        buy_adjust = average_price_diff / regularMarketPrice
                        # how much cash does thr trader want to use
                        adjusted_cash = (buy_adjust + 1) * cash
                        # how many shares to buy
                        buy_share_count = adjusted_cash / regularMarketPrice
                        # 2 decimals at mast
                        trades[ticker] = round(max(buy_share_count * amplify, 0), 2)

                    # save to a BigQuery table
                    rows_to_insert = [
                        {"account": 10000, "recommendation": str(trades), "updated": str(datetime.datetime.utcnow())}
                    ]
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

                    return serialize_exceptions(trades)
                else:
                    return "missing query string tickers", HTTPStatus.BAD_REQUEST

            else:
                return "JSON is invalid, or missing headers of {0}".format(header_params), HTTPStatus.BAD_REQUEST
        else:
            return "content_type != 'application/json", HTTPStatus.BAD_REQUEST
    else:
        return abort(404)
