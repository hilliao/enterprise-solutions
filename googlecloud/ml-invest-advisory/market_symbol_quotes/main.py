import os

import functions_framework

from tradestation import get_tradestation_realtime_quotes
from sinotrade import get_sinotrade_snapshots
import requests


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



@functions_framework.http
def get_us_stock_quotes(http_request):
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
            stock_symbol_quotes = get_tradestation_realtime_quotes(tickers=stock_symbols)
            return stock_symbol_quotes, 200
        except Exception as e:
            return {'error': str(e)}, 500
    else:
        return {'error': 'Invalid request method.'}, 405
