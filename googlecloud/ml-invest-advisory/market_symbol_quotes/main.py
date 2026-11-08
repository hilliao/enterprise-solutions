import importlib
import json
import os
import traceback

import functions_framework
import requests
from alpaca.common.exceptions import APIError as AlpacaApiError

from sinotrade import get_sinotrade_quotes
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
    Taiwan stock quotes from SinoTrade for ?symbols=2330,006208, keyed by symbol, with the same keys as
    get_us_ticker_quotes plus "currency"; see snapshot_to_quote() in sinotrade.py. Needs $TW_NATIONAL_ID.

    Sample request; ?tickers= works too:
        curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
          "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-tw-ticker-quotes?symbols=2330,NOPE99"

    Sample response after the close on Friday 2026-11-06. Prices are in TWD. Unknown symbols are left out of the
    body and listed in the X-SinoTrade-Errors header:
        HTTP/2 200
        x-sinotrade-errors: [{"symbol": "NOPE99", "error": "SinoTrade has no contract for the symbol"}]

        {"2330": {"symbol": "2330", "price": 2135.0, "previous-close": 2240.0, "net-change": -105.0,
                  "net-change-%": -4.68, "trade-time": "2026-11-06T06:30:00Z", "open": 2020.0, "high": 2195.0,
                  "low": 2020.0, "bid": 2135.0, "ask": 2140.0, "currency": "TWD"}}
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
        quotes, symbol_errors = get_sinotrade_quotes(symbols)
        # Keep the response body as {symbol: quote}; symbols SinoTrade could not quote go in a header.
        headers = {'X-SinoTrade-Errors': json.dumps(symbol_errors)} if symbol_errors else {}
        return quotes, 200, headers
    except Exception as error:
        log(text=f"get_tw_ticker_quotes failed: {traceback.format_exc()}", severity=LOG_SEVERITY_ERROR)
        return {'error': str(error)}, 500


@functions_framework.http
def get_us_ticker_quotes(http_request):
    """
    US stock quotes from Alpaca for ?tickers=VOO,QQQ, keyed by symbol; see snapshot_to_quote() in alpaca-quotes.py.

    Sample request; ?symbols= works too:
        curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
          "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-us-ticker-quotes?tickers=VOO,QQQ"

    Sample response for ?tickers=VOO,XYZQ after the close on Friday 2026-11-06. Symbols Alpaca can't quote are left
    out of the body and listed in the X-Alpaca-Errors header; open, high, low, close and volume are left out in
    pre-market:
        HTTP/2 200
        x-alpaca-errors: [{"symbol": "XYZQ", "error": "Alpaca returned no snapshot for the symbol"}]

        {"VOO": {"symbol": "VOO", "price": 675.9, "previous-close": 673.94, "net-change": 1.96, "net-change-%": 0.29,
                 "trade-time": "2026-11-06T21:00:03Z", "open": 675.435, "high": 681.44, "low": 675.34, "close": 676.02,
                 "volume": 109275.0, "bid": 655.12, "ask": 696.49}}
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
