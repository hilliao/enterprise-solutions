import importlib
import json
import os
import traceback

import functions_framework
import requests
from alpaca.common.exceptions import APIError as AlpacaApiError

from sinotrade import get_sinotrade_snapshots, snapshot_to_dict
from structured_logging import log, LOG_SEVERITY_ERROR

# alpaca-quotes.py has a hyphen in its name, so it can't be imported with an import statement.
alpaca_quotes = importlib.import_module('alpaca-quotes')

METADATA_PROJECT_ID_URL = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'


def get_project_id_from_metadata():
    """Fetches the Google Cloud project ID from the Metadata Server; returns None if the server can't be reached."""
    try:
        # The Metadata Server requires the Metadata-Flavor header on every request.
        response = requests.get(METADATA_PROJECT_ID_URL, headers={'Metadata-Flavor': 'Google'}, timeout=1)
        response.raise_for_status()
        return response.text.strip()
    except requests.exceptions.RequestException as error:
        log(text=f"Error accessing Metadata Server: {error}", severity=LOG_SEVERITY_ERROR)
        return None


def set_project_id_on_cloud_run():
    """
    Sets $PROJECT_ID, which gcp_data_access.py reads secrets from, when running in Cloud Run ($K_SERVICE is set).
    The Metadata Server is asked once per instance; locally, set $PROJECT_ID yourself.
    """
    if not os.environ.get('K_SERVICE') or os.environ.get('PROJECT_ID'):
        return
    project_id = get_project_id_from_metadata()
    if project_id:
        os.environ['PROJECT_ID'] = project_id


def parse_symbols(symbols_param: str) -> list[str]:
    """Splits a comma-separated query parameter into symbols, dropping blanks and surrounding whitespace."""
    return [symbol.strip() for symbol in symbols_param.split(',') if symbol.strip()]


@functions_framework.http
def get_tw_ticker_quotes(http_request):
    """
    Taiwan stock quotes from SinoTrade for ?symbols=2330,006208; needs $TW_NATIONAL_ID, see sinotrade.py.

    Sample request:
        curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
          "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-tw-ticker-quotes?symbols=2330"

    Sample response, one snapshot_to_dict() per symbol, after the close on Friday 2026-11-06:
        HTTP/2 200
        [{"ts": 1793975400000000000, "code": "2330", "exchange": "TSE", "open": 2020.0, "high": 2195.0,
          "low": 2020.0, "close": 2135.0, "tick_type": "Sell", "change_price": -105.0, "change_rate": -4.68,
          "change_type": "Down", "average_price": 2093.18, "volume": 106, "total_volume": 97065,
          "amount": 226310000, "total_amount": 203179565000, "yesterday_volume": 36585.0, "buy_price": 2135.0,
          "buy_volume": 12.0, "sell_price": 2140.0, "sell_volume": 1039, "volume_ratio": 2.65}]

    An unknown symbol fails the whole request:
        HTTP/2 500
        {"error": "'NOPE99'"}
    """
    if http_request.method != 'GET':
        return {'error': 'Invalid request method.'}, 405

    set_project_id_on_cloud_run()
    symbols_param = http_request.args.get('symbols', '')
    if not symbols_param:
        return {'error': 'Missing "symbols" query parameter.'}, 400
    symbols = parse_symbols(symbols_param)
    if not symbols:
        return {'error': 'No valid stock symbols provided.'}, 400

    try:
        snapshots = get_sinotrade_snapshots(stock_symbols=symbols)
        return [snapshot_to_dict(snapshot) for snapshot in snapshots], 200
    except Exception as error:
        log(text=f"get_tw_ticker_quotes failed: {traceback.format_exc()}", severity=LOG_SEVERITY_ERROR)
        return {'error': str(error)}, 500


# OBSOLETE: the TradeStation API is retired; use get_us_ticker_quotes (Alpaca). get_us_stock_quotes is commented
# out so main.py doesn't import tradestation_obsolete.py, and deploy.sh no longer deploys it. It used:
# from tradestation_obsolete import get_tradestation_realtime_quotes, TradeStationApiError
# @functions_framework.http
# def get_us_stock_quotes(http_request):
#     if http_request.method != 'GET':
#         return {'error': 'Invalid request method.'}, 405
#
#     set_project_id_on_cloud_run()
#     symbols_param = http_request.args.get('symbols', http_request.args.get('tickers', ''))
#     if not symbols_param:
#         return {'error': 'Missing "symbols" query parameter.'}, 400
#     symbols = parse_symbols(symbols_param)
#     if not symbols:
#         return {'error': 'No valid stock symbols provided.'}, 400
#
#     try:
#         quotes, symbol_errors = get_tradestation_realtime_quotes(tickers=symbols)
#         # Keep the response body as {symbol: quote}; symbols TradeStation could not quote go in a header.
#         headers = {'X-TradeStation-Errors': json.dumps(symbol_errors)} if symbol_errors else {}
#         return quotes, 200, headers
#     except TradeStationApiError as error:
#         return {'error': str(error), 'detail': error.detail}, 500
#     except Exception as error:
#         log(text=f"get_us_stock_quotes failed: {traceback.format_exc()}", severity=LOG_SEVERITY_ERROR)
#         return {'error': str(error)}, 500


@functions_framework.http
def get_us_ticker_quotes(http_request):
    """
    US stock quotes from Alpaca, in the same request and response format as the obsolete get_us_stock_quotes.

    Sample request; ?symbols= works too:
        curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
          "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-us-ticker-quotes?tickers=VOO,QQQ"

    Sample response after the close on Friday 2026-11-06. Symbols Alpaca can't quote are left out of the body and
    listed in the X-Alpaca-Errors header; Open, High, Low, Close, Volume and VWAP are left out in pre-market:
        HTTP/2 200
        x-alpaca-errors: [{"Symbol": "XYZQ", "Error": "Alpaca returned no snapshot for the symbol"}]

        {"VOO": {"Symbol": "VOO", "Last": 675.9, "PreviousClose": 673.94, "NetChange": 1.9599999999999227,
                 "NetChangePct": 0.2908270765943441, "PreviousVolume": 170486.0, "TradeTime": "2026-11-06T21:00:03Z",
                 "LastSize": 120.0, "LastVenue": "V", "Open": 675.435, "High": 681.44, "Low": 675.34,
                 "Close": 676.02, "Volume": 109275.0, "VWAP": 678.078609, "Bid": 655.12, "BidSize": 40.0,
                 "Ask": 696.49, "AskSize": 40.0}}
    """
    if http_request.method != 'GET':
        return {'error': 'Invalid request method.'}, 405

    set_project_id_on_cloud_run()
    symbols_param = http_request.args.get('symbols', http_request.args.get('tickers', ''))
    if not symbols_param:
        return {'error': 'Missing "symbols" query parameter.'}, 400
    symbols = parse_symbols(symbols_param)
    if not symbols:
        return {'error': 'No valid stock symbols provided.'}, 400

    try:
        quotes, symbol_errors = alpaca_quotes.get_alpaca_realtime_quotes(tickers=symbols)
        # Keep the response body as {symbol: quote}; symbols Alpaca could not quote go in a header.
        headers = {'X-Alpaca-Errors': json.dumps(symbol_errors)} if symbol_errors else {}
        return quotes, 200, headers
    except AlpacaApiError as error:
        log(text=f"Alpaca API returned {error.status_code}: {error}", severity=LOG_SEVERITY_ERROR)
        return {'error': f"Alpaca API returned {error.status_code}", 'detail': str(error)}, 500
    except Exception as error:
        log(text=f"get_us_ticker_quotes failed: {traceback.format_exc()}", severity=LOG_SEVERITY_ERROR)
        return {'error': str(error)}, 500
