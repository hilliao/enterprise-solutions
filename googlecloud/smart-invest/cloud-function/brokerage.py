import datetime
import json
import math
import os
from concurrent import futures
from concurrent.futures.thread import ThreadPoolExecutor
from http import HTTPStatus

import requests
from google.cloud import storage

from cloud_native import LOG_SEVERITY_DEBUG
from cloud_native import LOG_SEVERITY_ERROR
from cloud_native import LOG_SEVERITY_WARNING
from cloud_native import get_secret_value
from cloud_native import log

access_token = None
# Trade station has access token keep_alive=20 minutes per https://api.tradestation.com/docs/fundamentals/authentication/refresh-tokens/
trade_station_access_token_keep_alive = datetime.timedelta(minutes=19)
trade_station_url = 'https://api.tradestation.com/v3'
trade_station_market_data = '/marketdata/stream/quotes/{symbols}'
trade_station_token_url = "https://signin.tradestation.com/oauth/token"


class Quote:
    def __init__(self, json_quote):
        if 'fiftyDayAverage' in json_quote:
            self.average50days = json_quote['fiftyDayAverage']
        if 'twoHundredDayAverage' in json_quote:
            self.average200days = json_quote['twoHundredDayAverage']
        if 'Last' in json_quote:
            self.latest_price = float(json_quote['Last'])
        if 'regularMarketPrice' in json_quote:
            self.cached_price = json_quote['regularMarketPrice']
        self.raw_dict = json_quote

    def diff_price_moving_averages(self):
        if hasattr(self, 'average200days') and hasattr(self, 'average50days') and self.latest_ticker_price():
            return self.latest_ticker_price() - (self.average200days + self.average50days) / 2
        else:
            return None

    def latest_ticker_price(self):
        if hasattr(self, 'latest_price'):
            return self.latest_price
        elif hasattr(self, 'cached_price'):
            return self.cached_price
        else:
            return None


# try to get the cached Yahoo Finance quotes first. If no cached quotes, return the trade station quotes.
# If both quotes exist, the keys in trade station quotes would override the key,value items from Yahoo Finance quotes.
def get_cached_or_realtime_quote(bucket, ticker):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket)
    gcs_path = "{0}/{1}.json".format(os.environ.get('FOLDER'), ticker)
    blob = bucket.blob(gcs_path)
    try:
        json_str = blob.download_as_string().decode()
        json_quote = json.loads(json_str)
    except Exception as err:
        log(text='Reading quote of {} from Google cloud storage at gs://{}/{} failed: {}'
            .format(ticker, os.environ.get('BUCKET'), gcs_path, str(err)),
            severity=LOG_SEVERITY_WARNING)
        # hoping the real time quote API will succeed
        json_quote = {}
    # attempt to call Trade Station API to get real time price quote
    refresh_global_access_token()

    for key, value in access_token.items():
        if 'token' in value:
            trade_station_quote = '{}{}'.format(trade_station_url, trade_station_market_data.format(symbols=ticker))
            headers = {
                'Authorization': 'Bearer {}'.format(value['token'])
            }
            with requests.request("GET", trade_station_quote, headers=headers, stream=True) as quote_response:
                if quote_response.status_code == HTTPStatus.OK:
                    for chunk in quote_response.iter_content(1024 * 10, decode_unicode=True):
                        ts_quote = json.loads(chunk)
                        break

                    json_quote.update(ts_quote)
                    log(text='TradeStation get quote of {} succeeded: {}'.format(ticker, quote_response.text),
                        severity=LOG_SEVERITY_DEBUG)
                    # after using the 1st account's access token, no need to get quotes as other accounts
                    break
                else:
                    error_text = 'TradeStation get quote of {} failed with {}: {}'.format(ticker,
                                                                                          quote_response.status_code,
                                                                                          quote_response.text)
                    log(text=error_text, severity=LOG_SEVERITY_ERROR)
                    return Exception(error_text)
        else:
            error_text = 'Failed to get TradeStation access token from refresh token in secret {}'.format(
                os.environ.get('SECRET_NAME_TradeStation_OAuth0'))
            log(text=error_text, severity=LOG_SEVERITY_ERROR)
            return Exception(error_text)

    quote = Quote(json_quote)
    return quote


def refresh_global_access_token():
    """
    refresh access token if the last refresh time gets close to 20 minutes ago
    20 minutes subject to change per https://api.tradestation.com/docs/fundamentals/authentication/refresh-tokens/
    :return:
    """
    global access_token

    if access_token is None:
        access_token = refresh_access_token()
    else:
        do_refresh_access_token = False
        for key, value in access_token.items():
            if not value['last_modified'] or \
                    datetime.datetime.now() - value['last_modified'] > trade_station_access_token_keep_alive:
                do_refresh_access_token = True
                break
        if do_refresh_access_token:
            access_token = refresh_access_token()

    return access_token


def refresh_access_token():
    """
    secret is in the format of:
    {
      "account_number_0":
      {
        "client_id": "123",
        "client_secret": "bbb",
        "refresh_token": "ccc"
      },
      "account_number_1":
      {
        "client_id": "234",
        "client_secret": "jjj",
        "refresh_token": "zzz"
      }
    }
    :return:
    {
      "account_number_0":
      {
        "token": "aaa",
        "last_modified": datetime.datetime
      },
      "account_number_1":
      {
        "token": "hhh",
        "last_modified": datetime.datetime
      }
    }
    """
    TradeStation_OAuth0 = get_secret_value('SECRET_NAME_TradeStation_OAuth0')
    TradeStation_OAuth0_dict = json.loads(TradeStation_OAuth0)
    access_token_dict = {}

    for key, inner_dict in TradeStation_OAuth0_dict.items():
        client_id = inner_dict['client_id']
        client_secret = inner_dict['client_secret']
        refresh_token = inner_dict['refresh_token']

        # building the payload for trade station OAuth API
        payload = 'grant_type=refresh_token&client_id={}&client_secret={}&refresh_token={}'.format(
            client_id, client_secret, refresh_token
        )
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

        # invoke trade station OAuth API
        token_response = requests.request("POST", trade_station_token_url, headers=headers, data=payload)

        if token_response.status_code == HTTPStatus.OK:
            local_access_token = token_response.json()['access_token']
            last_modified = datetime.datetime.now()
            local_access_token = {
                'token': local_access_token,
                'last_modified': last_modified
            }
            access_token_dict[key] = local_access_token
        else:
            token_response.raise_for_status()

    return access_token_dict


MAX_WORKERS = 10


# Cached quotes are from Yahoo Finance where twoHundredDayAverage and fiftyDayAverage keys exist.
# Real time quotes from trade station don't have those averages.
def get_cached_or_realtime_quotes(bucket, tickers):
    thread_results = {}
    with ThreadPoolExecutor(max_workers=int(MAX_WORKERS)) as executor:
        for ticker in tickers:
            thread_results[ticker] = executor.submit(get_cached_or_realtime_quote, bucket, ticker)

        futures.wait(thread_results.values(), return_when=futures.ALL_COMPLETED)

    for ticker in thread_results:
        # exception thrown from .result() method if any exception happened
        try:
            thread_results[ticker] = thread_results[ticker].result()
        except Exception as ex:
            thread_results[ticker] = 'Exception type {} happened: {}'.format(type(ex), ex)

    return thread_results


# limit_order_off is how much less than the quoted price for a limit trade order. 0.1 means for a quoted stock that's
# $100, the limit order is set at $90. Generally, you'd want to set the price to be less than the quoted price.
def execute_trade_order(trade_orders: dict, account_id: str, duration: str = 'GTC', limit_order_off: float = 0.01):
    # API doc: https://api.tradestation.com/docs/specification/#operation/ConfirmGroupOrder
    trade_station_order_api = "{}/orderexecution/ordergroups".format(trade_station_url)

    orders = []
    # trade_orders dict may have values of Exceptions where recommendations failed
    for ticker, order in trade_orders.items():
        if isinstance(order, Exception):
            continue

        orders.append({
            "AccountID": account_id,
            "Symbol": ticker,
            "Quantity": str(math.floor(order.shares)),
            # TODO: make order type a parameter
            "OrderType": "Limit",
            # 100 is for rounding to 2 decimals
            "LimitPrice": str(math.floor(order.price * (1 - limit_order_off) * 100) / 100.0),
            "TradeAction": "BUY",
            # Expand TimeInForce.duration parameter at https://api.tradestation.com/docs/specification/#operation/PlaceOrder
            # to see available enumerations
            "TimeInForce": {"Duration": duration},
            "Route": "Intelligent"
        })

    payload = {
        "Type": "NORMAL",
        "Orders": orders}

    refresh_global_access_token()
    headers = {
        "content-type": "application/json",
        "Authorization": "Bearer {}".format(access_token[account_id]['token'])
    }

    order_exec_response = requests.request("POST", trade_station_order_api, json=payload, headers=headers)
    trade_orders['executions'] = {'status': order_exec_response.status_code,
                                  'results': json.loads(order_exec_response.text),
                                  'reason': order_exec_response.reason,
                                  'url': trade_station_order_api}
    if not order_exec_response.status_code == HTTPStatus.OK:
        log(text='Trade station order execution failed at {} with status {}, reason {}: {}'.format(
            trade_station_order_api,
            order_exec_response.status_code,
            order_exec_response.reason,
            order_exec_response.text),
            severity=LOG_SEVERITY_ERROR)

    return trade_orders


def yh_finance_get_quotes(tickers):
    yh_finance_url = "https://yh-finance.p.rapidapi.com/market/v2/get-quotes"
    # example: "QQQ,ONEQ,IVV,VOO,JETS,VHT,VDE,VFH,VTWO,BRK-B,ACN,AMD,GOOGL,AMZN,MSFT,MRVL,FB,QCOM,CRM,SNAP,TSM,BHP,RIO,EXPE,BKNG,HD"
    querystring = {
        "region": "US",
        "symbols": tickers
    }
    env_var_secret_name = 'SECRET_NAME_YH_API_KEY'
    YH_API_key = get_secret_value(env_var_secret_name)
    headers = {
        "X-RapidAPI-Host": "yh-finance.p.rapidapi.com",
        "X-RapidAPI-Key": YH_API_key
    }
    yh_finance_res = requests.request("GET", yh_finance_url, headers=headers, params=querystring)
    return yh_finance_res
