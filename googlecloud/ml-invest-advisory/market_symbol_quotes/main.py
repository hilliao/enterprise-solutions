import importlib
import json
import os
import traceback

import functions_framework
from alpaca.common.exceptions import APIError as AlpacaApiError

from structured_logging import log, LOG_SEVERITY_ERROR
from sinotrade import get_sinotrade_snapshots
import requests

# alpaca-quotes.py has a hyphen in its name, so it can't be imported with an import statement.
alpaca_quotes = importlib.import_module('alpaca-quotes')


def get_project_id_from_metadata():
    """Fetches the Google Cloud Project ID from the Metadata Server."""
    metadata_url = "http://metadata.google.internal/computeMetadata/v1/project/project-id"

    # Required header for all Metadata Server requests
    metadata_headers = {'Metadata-Flavor': 'Google'}

    try:
        response = requests.get(metadata_url, headers=metadata_headers, timeout=1)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.text.strip()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing Metadata Server: {e}")
        # Handle the error appropriately, perhaps by logging and exiting
        return None




@functions_framework.http
def get_tw_stock_quotes(http_request):
    if http_request.method == 'GET':
        stock_symbols_str = http_request.args.get('symbols', '')
        if os.environ.get('K_SERVICE'):  # Check if running in Google Cloud Run
            os.environ['PROJECT_ID'] = get_project_id_from_metadata()
        if not stock_symbols_str:
            return {'error': 'Missing "symbols" query parameter.'}, 400

        stock_symbols = [s.strip() for s in stock_symbols_str.split(',') if s.strip()]
        if not stock_symbols:
            return {'error': 'No valid stock symbols provided.'}, 400

        try:
            stock_symbol_quotes = get_sinotrade_snapshots(stock_symbols=stock_symbols)
            return [q.json() for q in stock_symbol_quotes], 200
        except Exception as e:
            return {'error': str(e)}, 500
    else:
        return {'error': 'Invalid request method.'}, 405



# OBSOLETE: the TradeStation API is retired; use get_us_ticker_quotes (Alpaca). get_us_stock_quotes is commented
# out so main.py doesn't import tradestation_obsolete.py, and deploy.sh no longer deploys it. It used:
# from tradestation_obsolete import get_tradestation_realtime_quotes, TradeStationApiError
# @functions_framework.http
# def get_us_stock_quotes(http_request):
#     if http_request.method == 'GET':
#         stock_symbols_str = http_request.args.get('symbols', http_request.args.get('tickers', ''))
#         if os.environ.get('K_SERVICE'):  # Check if running in Google Cloud Run
#             os.environ['PROJECT_ID'] = get_project_id_from_metadata()
#         if not stock_symbols_str:
#             return {'error': 'Missing "symbols" query parameter.'}, 400
#
#         stock_symbols = [s.strip() for s in stock_symbols_str.split(',') if s.strip()]
#         if not stock_symbols:
#             return {'error': 'No valid stock symbols provided.'}, 400
#
#         try:
#             stock_symbol_quotes, symbol_errors = get_tradestation_realtime_quotes(tickers=stock_symbols)
#             # Keep the response body as {symbol: quote}; symbols TradeStation could not quote go in a header.
#             headers = {'X-TradeStation-Errors': json.dumps(symbol_errors)} if symbol_errors else {}
#             return stock_symbol_quotes, 200, headers
#         except TradeStationApiError as e:
#             return {'error': str(e), 'detail': e.detail}, 500
#         except Exception as e:
#             log(text=f"get_us_stock_quotes failed: {traceback.format_exc()}", severity=LOG_SEVERITY_ERROR)
#             return {'error': str(e)}, 500
#     else:
#         return {'error': 'Invalid request method.'}, 405


@functions_framework.http
def get_us_ticker_quotes(http_request):
    """US stock quotes from Alpaca, in the same request and response format as the obsolete get_us_stock_quotes."""
    if http_request.method == 'GET':
        stock_symbols_str = http_request.args.get('symbols', http_request.args.get('tickers', ''))
        if os.environ.get('K_SERVICE'):  # Check if running in Google Cloud Run
            os.environ['PROJECT_ID'] = get_project_id_from_metadata()
        if not stock_symbols_str:
            return {'error': 'Missing "symbols" query parameter.'}, 400

        stock_symbols = [s.strip() for s in stock_symbols_str.split(',') if s.strip()]
        if not stock_symbols:
            return {'error': 'No valid stock symbols provided.'}, 400

        try:
            stock_symbol_quotes, symbol_errors = alpaca_quotes.get_alpaca_realtime_quotes(tickers=stock_symbols)
            # Keep the response body as {symbol: quote}; symbols Alpaca could not quote go in a header.
            headers = {'X-Alpaca-Errors': json.dumps(symbol_errors)} if symbol_errors else {}
            return stock_symbol_quotes, 200, headers
        except AlpacaApiError as e:
            log(text=f"Alpaca API returned {e.status_code}: {e}", severity=LOG_SEVERITY_ERROR)
            return {'error': f"Alpaca API returned {e.status_code}", 'detail': str(e)}, 500
        except Exception as e:
            log(text=f"get_us_ticker_quotes failed: {traceback.format_exc()}", severity=LOG_SEVERITY_ERROR)
            return {'error': str(e)}, 500
    else:
        return {'error': 'Invalid request method.'}, 405
