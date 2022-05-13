import os

import functions_framework
from google.cloud import storage
from flask import abort
import json
import requests
from http import HTTPStatus


# https://stock-quotes-slnskhfzsa-uw.a.run.app/?tickers=GOOGL,IVV,AMZN
@functions_framework.http
def stock_quotes(http_request):
    # read stock quotes
    if http_request.method == 'GET':
        gs_uri = http_request.args.get('gs_uri')  # gs://test-vpc-341000/mock/quotes.json
        tickers = http_request.args.get('tickers')  # GOOGL,IVV
        bucket = os.environ.get('BUCKET')

        if tickers:
            list_tickers = tickers.split(',')
            quotes = {}
            for ticker in list_tickers:
                quotes[ticker] = get_cached_quote(bucket, ticker)

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
        headers = {
            "X-RapidAPI-Host": "yh-finance.p.rapidapi.com",
            "X-RapidAPI-Key": os.environ.get('X-RAPIDAPI-KEY')
        }

        response = requests.request("GET", url, headers=headers, params=querystring)
        storage_client = storage.Client()
        bucket = storage_client.get_bucket('test-vpc-341000')

        counter = 0
        saved_quotes = {}

        for tickers in querystring['symbols'].split(','):
            gcs_file = bucket.blob('quotes/{}.json'.format(tickers))
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


def get_cached_quote(bucket, ticker):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket)
    blob = bucket.blob("quotes/{0}.json".format(ticker))
    json_str = blob.download_as_string().decode()
    json_quote = json.loads(json_str)
    return json_quote


# curl -X PUT https://trade-recommendation-slnskhfzsa-uw.a.run.app/?tickers=IVV,GOOGL,FB -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"cash":11111, "amplify": 1}' -i
@functions_framework.http
def get_trade_recommendation(http_request):
    if http_request.method == 'PUT':
        content_type = http_request.headers['content-type']
        if content_type == 'application/json':
            request_json = http_request.get_json(silent=True)
            header_params = ['cash', 'amplify']
            if request_json and all(item in request_json for item in header_params):
                tickers = http_request.args.get('tickers')  # GOOGL,IVV
                bucket = os.environ.get('BUCKET')

                if tickers:
                    list_tickers = tickers.split(',')
                    trades = {}
                    for ticker in list_tickers:
                        ticker_quote = get_cached_quote(bucket, ticker)
                        cash = int(request_json['cash']) / len(list_tickers)
                        amplify = request_json['amplify']
                        fiftyDayAverage = ticker_quote['fiftyDayAverage']
                        twoHundredDayAverage = ticker_quote['twoHundredDayAverage']
                        regularMarketPrice = ticker_quote['regularMarketPrice']

                        # average of the moving averages minus the current stock price
                        average_price_diff = ((fiftyDayAverage + twoHundredDayAverage) / 2 - regularMarketPrice)
                        # how much more or less does the trader want to buy
                        buy_adjust = average_price_diff / regularMarketPrice
                        # how much cash does thr trader want to use
                        adjusted_cash = (buy_adjust + 1) * cash
                        # how many shares to buy
                        buy_share_count = adjusted_cash / regularMarketPrice
                        trades[ticker] = max(buy_share_count * amplify, 0)

                    return trades
                else:
                    return "missing query string tickers", HTTPStatus.BAD_REQUEST

            else:
                return "JSON is invalid, or missing headers of {0}".format(header_params), HTTPStatus.BAD_REQUEST