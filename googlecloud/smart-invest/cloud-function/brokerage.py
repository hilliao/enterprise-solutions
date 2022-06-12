import datetime
import json
import math
import os
from concurrent import futures
from concurrent.futures.thread import ThreadPoolExecutor
from http import HTTPStatus

import requests
from google.cloud import storage

from cloud_native import log
from cloud_native import LOG_SEVERITY_DEBUG
from cloud_native import LOG_SEVERITY_ERROR
from cloud_native import LOG_SEVERITY_WARNING
from cloud_native import get_secret_value

access_token = {
    'token': None,
    'last_modified': None
}
# Trade station has access token keep_alive=20 minutes
trade_station_access_token_keep_alive = datetime.timedelta(minutes=19)
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
    refresh_global_access_token()

    if 'token' in access_token:
        trade_station_quote = '{}{}'.format(trade_station_url, trade_station_market_data.format(symbols=ticker))
        headers = {
            'Authorization': 'Bearer {}'.format(access_token['token'])
        }
        with requests.request("GET", trade_station_quote, headers=headers, stream=True) as quote_response:
            if quote_response.status_code == HTTPStatus.OK:
                for chunk in quote_response.iter_content(1024 * 10, decode_unicode=True):
                    ts_quote = json.loads(chunk)
                    break

                json_quote.update(ts_quote)
                log(text='TradeStation get quote of {} succeeded: {}'.format(ticker, quote_response.text),
                    severity=LOG_SEVERITY_DEBUG)
            else:
                log(text='TradeStation get quote of {} failed with {}: {}'.format(ticker,
                                                                                  quote_response.status_code,
                                                                                  quote_response.text),
                    severity=LOG_SEVERITY_ERROR)
    else:
        log(text='Failed to get TradeStation access token from refresh token in secret {}'.format(
            os.environ.get('SECRET_NAME_REFRESH_TOKEN')), severity=LOG_SEVERITY_ERROR)

    return json_quote


# refresh access token if the last refresh time gets close to 20 minutes ago
def refresh_global_access_token():
    global access_token
    if not access_token['last_modified'] or \
            datetime.datetime.utcnow() - access_token['last_modified'] > trade_station_access_token_keep_alive:
        access_token = refresh_access_token()


def refresh_access_token():
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
        local_access_token = token_response.json()['access_token']
        last_modified = datetime.datetime.utcnow()
        local_access_token = {
            'token': local_access_token,
            'last_modified': last_modified
        }
    else:
        local_access_token = {
            'token': None,
            'last_modified': None
        }

    return local_access_token


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


def execute_trade_order(trade_orders: dict, account_id: str):
    trade_station_order_api = "{}/orderexecution/ordergroups".format(trade_station_url)

    orders = []
    for ticker, order in trade_orders.items():
        if isinstance(order, Exception):
            continue

        orders.append({
            "AccountID": account_id,
            "Symbol": ticker,
            "Quantity": str(math.floor(order['shares'])),
            # TODO: make order type a parameter
            "OrderType": "Limit",
            # TODO: make limit order price a parameter, 100 is for rounding to 2 decimals, 0.9 is hard coded
            "LimitPrice": str(math.floor(order['price'] * 0.9 * 100) / 100.0),
            "TradeAction": "BUY",
            # TODO: make order type a parameter, GTC means good til cancel
            "TimeInForce": {"Duration": "GTC"},
            "Route": "Intelligent"
        })

    payload = {
        "Type": "NORMAL",
        "Orders": orders}

    refresh_global_access_token()
    headers = {
        "content-type": "application/json",
        "Authorization": "Bearer {}".format(access_token['token'])
    }

    order_exec_response = requests.request("POST", trade_station_order_api, json=payload, headers=headers)
    if order_exec_response.status_code == HTTPStatus.OK:
        trade_orders['executions'] = {'status': order_exec_response.status_code,
                                      'results': json.loads(order_exec_response.text),
                                      'url': trade_station_order_api}
    else:
        log(text='Trade station order execution failed at {} with status {}: {}'.format(
            trade_station_order_api,
            order_exec_response.status_code,
            order_exec_response.text), severity=LOG_SEVERITY_ERROR)

    return trade_orders


def yh_finance_get_quotes(tickers):
    yh_finance_url = "https://yh-finance.p.rapidapi.com/market/v2/get-quotes"
    querystring = {"region": "US",
                   "symbols": tickers}  # "QQQ,ONEQ,IVV,VOO,JETS,VHT,VDE,VFH,VTWO,BRK-B,ACN,AMD,GOOGL,AMZN,MSFT,MRVL,FB,QCOM,CRM,SNAP,TSM,BHP,RIO,EXPE,BKNG,HD"
    env_var_secret_name = 'SECRET_NAME_YH_API_KEY'
    YH_API_key = get_secret_value(env_var_secret_name)
    headers = {
        "X-RapidAPI-Host": "yh-finance.p.rapidapi.com",
        "X-RapidAPI-Key": YH_API_key
    }
    yh_finance_res = requests.request("GET", yh_finance_url, headers=headers, params=querystring)
    return yh_finance_res
