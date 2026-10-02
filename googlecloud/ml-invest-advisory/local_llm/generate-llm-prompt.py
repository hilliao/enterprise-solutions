"""
This script generates an LLM prompt by combining portfolio holdings with real-time stock quotes.

Workflow:
1. Loads portfolio holdings (tickers and share counts) from a JSON file.
2. Fetches real-time stock quotes (Last, PreviousClose, etc.) from a Cloud Run service.
   - Uses `STOCK_QUOTES_CLOUD_RUN_URL` environment variable for the service URL.
   - Authenticates using `GOOGLE_APPLICATION_CREDENTIALS`.
3. Merges portfolio holdings with stock quotes.
4. Calculates:
   - Current Value (Shares * Last Price)
   - Previous Value (Shares * Previous Close)
   - Daily performance change (%)
   - Portfolio weights
5. Loads an LLM prompt template.
6. Injects the calculated portfolio data into the template.
7. Writes the final prompt to an output file.

Usage:
    python generate-llm-prompt.py --portfolio_file <path_to_portfolio.json> --llm_prompt_template <path_to_template.txt> [--output_prompt <path_to_output.txt>]

Environment Variables:
    GOOGLE_APPLICATION_CREDENTIALS: Path to service account key file (Required).
    STOCK_QUOTES_CLOUD_RUN_URL: URL of the stock quotes service (Optional, defaults to hardcoded URL).
"""
# SET GOOGLE_APPLICATION_CREDENTIALS environment variable
# https://cloud.google.com/docs/authentication/application-default-credentials

import argparse
import json
import os
import sys
import time

import google.auth.transport.requests
import requests
from google.oauth2 import id_token

DEFAULT_OUTPUT_PROMPT_FILE = "prompt.txt"
PORTFOLIO_DATA_PLACEHOLDER = "{{PORTFOLIO_HOLDING_DATA_JSON}}"
# Seconds to wait before each retry of a failed Cloud Run request: exponential backoff up to 16 seconds,
# then give up. 6 attempts over ~31 seconds of waiting.
CLOUD_RUN_RETRY_DELAYS = [1, 2, 4, 8, 16]
CLOUD_RUN_REQUEST_TIMEOUT = 60
# Exit code when the stock quotes endpoint still fails after all retries (sysexits EX_UNAVAILABLE).
# executors/gen-investment-report-realtime-nonstop.sh reports this exit code as a quotes endpoint failure.
EXIT_CODE_QUOTES_UNAVAILABLE = 69


def describe_request_failure(e: requests.exceptions.RequestException) -> str:
    """
    Describes a failed request for the terminal: the error and, if the server responded, its status code and body.

    The stock quotes Cloud Run function returns TradeStation errors in the body, e.g. a 500 with
    {"error": "TradeStation API returned 403 for url: ...", "detail": "<html>...403 Forbidden...</html>"},
    so the body is what explains the failure. JSON bodies are pretty-printed.
    """
    if e.response is None:
        return str(e)
    try:
        body = json.dumps(e.response.json(), indent=2)
    except ValueError:
        body = e.response.text
    return f"{e}\nResponse status: {e.response.status_code}\nResponse body:\n{body}"



def invoke_cloud_run(base_url: str, url: str) -> str:
    """
    Invokes a Cloud Run endpoint that requires authentication.

    This function automatically uses the service account credentials from the
    environment variable `GOOGLE_APPLICATION_CREDENTIALS` to authenticate
    against a Cloud Run endpoint.
    GOOGLE_APPLICATION_CREDENTIALS environment variable to generate an
    ID token for the request.

    Args:
        base_url (str): The URL of the Cloud Run endpoint visible in Google Cloud Console.
        url (str): The full URL of the Cloud Run endpoint to invoke.


    Returns:
        str: The text content of the response if successful.

    A failed request is retried after each delay in CLOUD_RUN_RETRY_DELAYS (1, 2, 4, 8, 16 seconds).

    Raises:
        Exception: If the HTTP request still fails after the last retry.
    """
    try:
        # The 'audience' for an ID token is the URL of the service being called.
        # This is a security measure to ensure the token is only used for this service.
        audience = base_url

        print(f"Authenticating for audience: {audience}")

        # Fetch the ID token using Application Default Credentials
        auth_req = google.auth.transport.requests.Request()
        identity_token = id_token.fetch_id_token(auth_req, audience)

        # Create the Authorization header
        headers = {
            "Authorization": f"Bearer {identity_token}"
        }

        print(f"Successfully obtained ID token. Making request at {url}")

        # Make the authenticated GET request, retrying failures with exponential backoff (CLOUD_RUN_RETRY_DELAYS)
        # so a failing endpoint isn't called in a tight loop.
        for attempt, retry_delay in enumerate(CLOUD_RUN_RETRY_DELAYS + [None], start=1):
            try:
                response = requests.get(url, headers=headers, timeout=CLOUD_RUN_REQUEST_TIMEOUT)
                # Raise an exception for bad status codes (4xx or 5xx)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                next_step = f"retrying in {retry_delay}s" if retry_delay is not None else \
                    f"giving up after {len(CLOUD_RUN_RETRY_DELAYS)} retries"
                print(f"ERROR: Cloud Run request attempt {attempt} failed, {next_step}: {describe_request_failure(e)}",
                      file=sys.stderr, flush=True)
                if retry_delay is None:
                    raise
                time.sleep(retry_delay)

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        raise


def merge_portfolio_share_prices(portfolio_holding_shares: dict, holding_prices: dict) -> dict:
    """
    Merges portfolio units into a dictionary of stock quotes.

    This function creates a deep copy of the stock_quotes to avoid
    modifying the original data structure.

    Args:
        portfolio_holding_shares (dict): A dictionary with tickers and their shares.        An example of the expected format is:
        {
            "AAAU": {"shares": 31.90},
            "QQQ": {"shares": 19.41},
            "NVDA": {"shares": 1},
            "GOOGL": {"shares": 3},
            "VOO": {"shares": 21.22}
        }

        holding_prices (dict): A dictionary with tickers and detailed quote info.        An example of the expected format is:
        ```json
        {
            "BRK.B": {
                "Ask": "488.39",
                "AskSize": "100",
                "Bid": "488.29",
                "BidSize": "200",
                "Close": "488.31",
                "DailyOpenInterest": "0",
                "High": "495.99991",
                "High52Week": "542.07001",
                "High52WeekTimestamp": "2025-05-02T00:00:00Z",
                "Last": "488.31",
                "LastSize": "100",
                "LastVenue": "ARCX",
                "Low": "485.79999",
                "Low52Week": "437.89999",
                "Low52WeekTimestamp": "2024-11-04T00:00:00Z",
                "MarketFlags": {
                    "IsBats": false,
                    "IsDelayed": false,
                    "IsHalted": false,
                    "IsHardToBorrow": false
                },
                "NetChange": "-8.08001",
                "NetChangePct": "-0.0163",
                "Open": "495.595",
                "PreviousClose": "496.39001",
                "PreviousVolume": "3566253",
                "Symbol": "BRK.B",
                "TickSizeTier": "0",
                "TradeTime": "2025-10-16T19:20:42Z",
                "VWAP": "490.191077224156",
                "Volume": "2747246"
            },
            "QQQ": {
                "Ask": "597.6",
                "AskSize": "100",
                "Bid": "597.

    Returns:
        dict: A new dictionary containing the merged data.
    """
    # Create a deep copy of the quotes to avoid changing the original dict
    merged_json = json.loads(json.dumps(holding_prices))

    # Loop through each ticker in the portfolio_units dictionary
    for ticker, share_count in portfolio_holding_shares.items():
        # Check if the ticker exists in quotes dict
        if ticker in merged_json:
            # If it exists, update the nested dictionary with the share counts
            merged_json[ticker].update(share_count)
        else:
            # If a ticker from portfolio_units is not in stock_quotes,
            # you could add it as a new entry. WARNING: this will likely cause error in subsequence data processing!
            merged_json[ticker] = share_count

    return merged_json


def calculate_portfolio_1day_diff_and_weight(portfolio_data: dict = None, cash_amount: float = 0) -> dict:
    """
    Calculates current and previous values for portfolio holdings from a portfolio dict
    or a default string. It also computes the total portfolio value. The resulting dict
    has the attributes easily understood by LLM.

    Args:
        portfolio_data (dict, optional): A dictionary containing portfolio holdings.
                                        If None, uses a default data structure.
                                        Each key in the dict is a ticker symbol (str).
                                        Each value is a dict with the following required attributes:
                                        - "shares" (float): The number of shares held.
                                        - "Last" (float): The last traded price of the stock.
                                        - "PreviousClose" (float): The previous closing price of the stock.
        cash_amount (float, optional): The amount of cash in the portfolio. Defaults to 0.

    Returns:
        dict: A dictionary containing the calculated values for each ticker
              and a '__SUM' key with the total portfolio values.
    """
    if portfolio_data is None:
        default_json_string = """
        {
          "NVDA": {"shares": 10.90, "Last": "183.16", "PreviousClose": "192.1"},
          "QQQ": {"shares": 19.41, "Last": "589.93", "PreviousClose": "610.70001"},
          "VOO": {"shares": 21.22, "Last": "600.51", "PreviousClose": "617.09998"}
        }
        """
        portfolio_data = json.loads(default_json_string)  # Load default from string if no data provided

    calculated = {}
    total_current_value = 0.0
    total_previous_value = 0.0

    failed_tickers = []

    # Process each ticker in the portfolio
    for ticker, attributes in portfolio_data.items():
        try:
            for required in ('shares', 'Last', 'PreviousClose'):
                if attributes.get(required) is None:
                    raise ValueError(f"'{required}' attribute missing; the stock quotes response has no "
                                     f"usable quote for this ticker")
            share_count = float(attributes.get('shares'))
            last_price = float(attributes.get('Last'))
            previous_close = float(attributes.get('PreviousClose'))

            current_value = share_count * last_price
            previous_value = share_count * previous_close

            # Store results as floating point numbers, rounded to 2 decimal places
            calculated[ticker] = {
                'Current Value': round(current_value, 2),
                'Previous Value': round(previous_value, 2),
                'shares': share_count,
                'single share change in percentage': str(
                    f"{float(attributes.get('NetChangePct', 0)):.2f}%",
                ),
            }

            # Add to the running totals
            total_current_value += current_value
            total_previous_value += previous_value

        except (ValueError, TypeError) as e:
            print(f"ERROR: ticker {ticker} has a data error: {e}", file=sys.stderr)
            failed_tickers.append(ticker)

    # Weights and totals would be wrong without every holding's value
    if failed_tickers:
        print(f"\nERROR: Cannot calculate portfolio values; missing or invalid quotes for "
              f"{len(failed_tickers)} tickers: {', '.join(failed_tickers)}", file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    # Add the '__SUM' key with the totals
    total_current_value += cash_amount
    total_previous_value += cash_amount
    calculated['__SUM'] = {
        'Current Value': round(total_current_value, 2),
        'Previous Value': round(total_previous_value, 2),
        'daily performance change in percentage': str(
            round((total_current_value - total_previous_value) / total_previous_value * 100, 2)) + '%'
    }
    calculated['__CASH'] = {
        'shares': cash_amount,
        'weight in percentage': str(round(cash_amount / calculated['__SUM']['Current Value'] * 100, 2)) + '%'
    }

    # Calculate the weight of each holding
    for ticker, attributes in calculated.items():
        if ticker not in ['__SUM', '__CASH']:
            attributes['weight in percentage'] = str(
                round(attributes['Current Value'] / calculated['__SUM']['Current Value'] * 100, 2)) + '%'

    return calculated


def load_portfolio_holding_file(file_path: str) -> tuple[dict, float]:
    """
    Loads portfolio share units from a JSON file.

    Args:
        file_path (str): The path to the JSON file.     An example of the expected format is:
        ```json
        {
          "NVDA": {
            "shares": 2050.0
          },
          "BIL": {
            "shares": 634.0
          },
          "__CASH": {
            "shares": 492.08
          }
        }
       
    Returns:
        tuple: A tuple containing:
            - dict: A dictionary containing the portfolio shares (excluding '__CASH').
            - float: The cash amount if present, otherwise 0.0.
    """
    portfolio_data = {}
    with open(file_path, 'r') as f:
        portfolio_data = json.load(f)

    cash_amount = portfolio_data.pop('__CASH', {}).get('shares', 0.0)

    return portfolio_data, cash_amount


def main():
    parser = argparse.ArgumentParser(description='Process portfolio data.')
    parser.add_argument('--portfolio_file', type=str, required=True, help=
    'The path to the portfolio units JSON file. The file should be in the format: {"TICKER": {"Units": <number>}}')
    parser.add_argument('--llm_prompt_template', type=str, required=True, help=
    f'The path to the LLM prompt template text file that contains {PORTFOLIO_DATA_PLACEHOLDER}.')
    parser.add_argument('--output_prompt', type=str, default=DEFAULT_OUTPUT_PROMPT_FILE, help=
    f'The output file name for the generated LLM prompt. Defaults to "{DEFAULT_OUTPUT_PROMPT_FILE}".')
    args = parser.parse_args()

    portfolio_holding_shares, cash_amount = load_portfolio_holding_file(args.portfolio_file)

    holding_prices = get_holding_prices(portfolio_holding_shares)

    portfolio_holding_share_prices = merge_portfolio_share_prices(portfolio_holding_shares, holding_prices)
    portfolio_holding_values_and_weights = calculate_portfolio_1day_diff_and_weight(portfolio_holding_share_prices,
                                                                                    cash_amount)
    num_lines_to_print = 15
    print(f"\n--- Portfolio value change from last trading day (top {num_lines_to_print} lines) ---")
    print('\n'.join(json.dumps(portfolio_holding_values_and_weights, indent=2).splitlines()[:num_lines_to_print]))

    # Read the prompt template
    with open(args.llm_prompt_template, 'r') as f:
        prompt_template = f.read()

    # Replace the placeholder with the JSON data
    llm_ready_prompt = prompt_template.replace(PORTFOLIO_DATA_PLACEHOLDER,
                                               json.dumps(portfolio_holding_values_and_weights, indent=2))

    if args.output_prompt == DEFAULT_OUTPUT_PROMPT_FILE:  # Check if the default output file name is used
        output_file_path = os.path.join(os.path.dirname(args.llm_prompt_template), args.output_prompt)
    else:
        output_file_path = args.output_prompt  # Use the provided path directly
    with open(output_file_path, 'w') as f:
        f.write(llm_ready_prompt)

    print(f"\nLLM prompt written to: {output_file_path}")


def get_holding_prices(portfolio_holdings: dict) -> dict:
    # The URL of the Cloud Run function
    cloud_run_base_url = "https://us-central1-hil-financial-services.cloudfunctions.net/trade_station_realtime_quotes"
    if "STOCK_QUOTES_CLOUD_RUN_URL" in os.environ:
        cloud_run_base_url = os.environ["STOCK_QUOTES_CLOUD_RUN_URL"]
        print(f"Using STOCK_QUOTES_CLOUD_RUN_URL from environment variable: {cloud_run_base_url}")
    else:
        print(f"STOCK_QUOTES_CLOUD_RUN_URL environment variable not set. Using default: {cloud_run_base_url}")

    tickers = list(portfolio_holdings.keys())
    cloud_run_url = f"{cloud_run_base_url}/?tickers={','.join(tickers)}"

    # Ensure the environment variable is set before running
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
        print("Error: The GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.", file=sys.stderr)
        print("Please set it to the path of your service account key file.", file=sys.stderr)
        sys.exit(1)

    try:
        # Call the function and print the result
        cloud_run_response = invoke_cloud_run(cloud_run_base_url, cloud_run_url)
        print("\n--- Parsing response from Cloud Run service to JSON ---")
        num_lines_to_print = 10
        try:
            holding_prices = json.loads(cloud_run_response)
            print(f"--- Parsed JSON Response (top {num_lines_to_print} lines) ---")
            print('\n'.join(json.dumps(holding_prices, indent=2).splitlines()[:num_lines_to_print]))
        except json.JSONDecodeError:
            print(f"\nERROR: Cloud Run response is not valid JSON:\n{cloud_run_response}", file=sys.stderr)
            sys.exit(1)


    except Exception as e:
        print(f"\nERROR: Failed to invoke Cloud Run endpoint: {e}. Please check your URL and permissions.",
              file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    # The service returns {"Error": ..., "Symbol": ...} instead of a quote for tickers it failed to fetch
    ticker_errors = {ticker: quote.get('Error') for ticker, quote in holding_prices.items()
                     if isinstance(quote, dict) and quote.get('Error')}
    if ticker_errors:
        print(f"\nERROR: Cloud Run service {cloud_run_base_url} returned errors instead of quotes for "
              f"{len(ticker_errors)} of {len(tickers)} tickers:", file=sys.stderr)
        for ticker, error in ticker_errors.items():
            print(f"  {ticker}: Error={error}", file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)
    return holding_prices


if __name__ == "__main__":
    main()
