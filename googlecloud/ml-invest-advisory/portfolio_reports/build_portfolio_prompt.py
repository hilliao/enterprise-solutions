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
5. Adds each ticker's full name ("Name") from SEC EDGAR, caching the SEC JSON files next to this script for 24 hours.
6. Loads an LLM prompt template.
7. Injects the calculated portfolio data into the template.
8. Writes the final prompt to an output file.

Usage:
    python build_portfolio_prompt.py --portfolio_file <path_to_portfolio.json> --llm_prompt_template <path_to_template.txt> [--output_prompt <path_to_output.txt>]

Environment Variables:
    GOOGLE_APPLICATION_CREDENTIALS: Path to service account key file (Required).
    STOCK_QUOTES_CLOUD_RUN_URL: URL of the stock quotes service (Required).
    SEC_USER_AGENT: User-Agent for SEC EDGAR requests, a name and contact email such as "Agent Identity ai-agent@example.com"
                    (Optional, defaults to DEFAULT_SEC_USER_AGENT).
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
# scripts/run-market-hours.sh reports this exit code as a quotes endpoint failure.
EXIT_CODE_QUOTES_UNAVAILABLE = 69
# Number of tickers printed to the terminal from the quotes and the portfolio values.
NUM_TICKERS_TO_PRINT = 3
# SEC EDGAR JSON files for ticker names. Company tickers (NVDA) have a title; ETF and mutual fund tickers (QQQ) only
# have a CIK, whose submissions have the registrant name.
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FUND_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# The SEC rejects requests without a User-Agent naming the requester and a contact email, e.g. python-requests'
# default User-Agent gets a 403. https://www.sec.gov/os/accessing-edgar-data
DEFAULT_SEC_USER_AGENT = "Portfolio Reports agent-finops@googlecloud.fr"
SEC_REQUEST_TIMEOUT = 30
# Seconds between SEC requests; the SEC allows at most 10 requests per second.
SEC_REQUEST_INTERVAL = 0.1
# Downloaded SEC JSON files are cached in this script's folder and downloaded again when older than 24 hours.
SEC_CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
SEC_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def condensed_json(data, max_keys: int) -> str:
    """
    Formats a dictionary as JSON for the terminal with each top-level key and its value on one line, e.g.:
    {
      "AAAU": {"Current Value": 49900.05, "Previous Value": 49997.25, "shares": 1215.0},
      "BIL": {"Current Value": 5952.05, "Previous Value": 5950.1, "shares": 65.0},
      ... 25 more
    }
    Only the first max_keys keys are printed; the "... N more" line makes the output not valid JSON when keys are left
    out. Values that aren't dictionaries are formatted as compact JSON on one line.
    """
    if not isinstance(data, dict):
        return json.dumps(data)
    lines = [f"  {json.dumps(key)}: {json.dumps(value)}" for key, value in list(data.items())[:max_keys]]
    if len(data) > max_keys:
        lines.append(f"  ... {len(data) - max_keys} more")
    return '{\n' + ',\n'.join(lines) + '\n}'


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


def merge_ticker_shares_and_prices(portfolio_ticker_shares: dict, ticker_prices: dict) -> dict:
    """
    Merges portfolio ticker shares into a dictionary of ticker prices (stock quotes).

    This function creates a deep copy of ticker_prices to avoid
    modifying the original data structure.

    Args:
        portfolio_ticker_shares (dict): A dictionary with tickers and their shares.        An example of the expected format is:
        {
            "AAAU": {"shares": 31.90},
            "QQQ": {"shares": 19.41},
            "NVDA": {"shares": 1},
            "GOOGL": {"shares": 3},
            "VOO": {"shares": 21.22}
        }

        ticker_prices (dict): A dictionary with tickers and detailed quote info. Prices, sizes and volumes are JSON
        numbers (calculate_portfolio_1day_diff_and_weight also accepts numeric strings).
        An example of the expected format is:
        ```json
        {
          "AAAU": {"Ask": 40.45, "AskSize": 100.0, "Bid": 38.07, "BidSize": 100.0, "Close": 39.41, "High": 39.68, "Last": 39.41, "LastSize": 200.0, "LastVenue": "V", "Low": 39.18, "NetChange": -0.265, "NetChangePct": -0.6679269061121628, "Open": 39.67, "PreviousClose": 39.675, "PreviousVolume": 42632.0, "Symbol": "AAAU", "TradeTime": "2026-10-23T19:59:38Z", "VWAP": 39.383618, "Volume": 45000.0},
          "BIL": {"Ask": 91.64, "AskSize": 129000.0, "Bid": 91.62, "BidSize": 5000.0, "Close": 91.63, "High": 91.635, "Last": 91.63, "LastSize": 255.0, "LastVenue": "V", "Low": 91.63, "NetChange": 0.03, "NetChangePct": 0.03275109170305801, "Open": 91.635, "PreviousClose": 91.6, "PreviousVolume": 583017.0, "Symbol": "BIL", "TradeTime": "2026-10-23T20:02:25Z", "VWAP": 91.631811, "Volume": 259721.0}
        }
        ```
        The quotes have no DailyOpenInterest, High52Week, High52WeekTimestamp, Low52Week, Low52WeekTimestamp,
        MarketFlags or TickSizeTier attributes. NetChangePct is a percentage, e.g. -0.67 means -0.67%.

    Returns:
        dict: A new dictionary containing the merged data.
    """
    # Create a deep copy of the quotes to avoid changing the original dict
    merged_ticker_data = json.loads(json.dumps(ticker_prices))

    # Loop through each ticker in the portfolio_ticker_shares dictionary
    for ticker, shares_attributes in portfolio_ticker_shares.items():
        # Check if the ticker exists in quotes dict
        if ticker in merged_ticker_data:
            # If it exists, update the nested dictionary with the share counts
            merged_ticker_data[ticker].update(shares_attributes)
        else:
            # If a ticker from portfolio_ticker_shares is not in ticker_prices,
            # you could add it as a new entry. WARNING: this will likely cause error in subsequence data processing!
            merged_ticker_data[ticker] = shares_attributes

    return merged_ticker_data


def calculate_portfolio_1day_diff_and_weight(ticker_shares_and_prices: dict = None, cash_amount: float = 0) -> dict:
    """
    Calculates current and previous values for portfolio holdings from a portfolio dict
    or a default string. It also computes the total portfolio value. The resulting dict
    has the attributes easily understood by LLM.

    Args:
        ticker_shares_and_prices (dict, optional): A dictionary containing portfolio holdings.
                                        If None, uses a default data structure.
                                        Each key in the dict is a ticker symbol (str).
                                        Each value is a dict with the following required attributes:
                                        - "shares" (float): The number of shares held.
                                        - "Last" (float): The last traded price of the stock.
                                        - "PreviousClose" (float): The previous closing price of the stock.
        cash_amount (float, optional): The amount of cash in the portfolio. Defaults to 0.

    Returns:
        dict: A dictionary containing the ticker_values values for each ticker
              and a '__SUM' key with the total portfolio values.
    """
    if ticker_shares_and_prices is None:
        default_json_string = """
        {
          "NVDA": {"shares": 10.90, "Last": "183.16", "PreviousClose": "192.1"},
          "QQQ": {"shares": 19.41, "Last": "589.93", "PreviousClose": "610.70001"},
          "VOO": {"shares": 21.22, "Last": "600.51", "PreviousClose": "617.09998"}
        }
        """
        ticker_shares_and_prices = json.loads(default_json_string)  # Load default from string if no data provided

    ticker_values = {}
    total_current_value = 0.0
    total_previous_value = 0.0

    failed_tickers = []

    # Process each ticker in the portfolio
    for ticker, attributes in ticker_shares_and_prices.items():
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
            ticker_values[ticker] = {
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
    ticker_values['__SUM'] = {
        'Current Value': round(total_current_value, 2),
        'Previous Value': round(total_previous_value, 2),
        'daily performance change in percentage': str(
            round((total_current_value - total_previous_value) / total_previous_value * 100, 2)) + '%'
    }
    ticker_values['__CASH'] = {
        'shares': cash_amount,
        'weight in percentage': str(round(cash_amount / ticker_values['__SUM']['Current Value'] * 100, 2)) + '%'
    }

    # Calculate the weight of each holding
    for ticker, attributes in ticker_values.items():
        if ticker not in ['__SUM', '__CASH']:
            attributes['weight in percentage'] = str(
                round(attributes['Current Value'] / ticker_values['__SUM']['Current Value'] * 100, 2)) + '%'

    return ticker_values


def load_portfolio_ticker_shares(file_path: str) -> tuple[dict, float]:
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
    with open(file_path, 'r') as f:
        portfolio_ticker_shares = json.load(f)

    cash_amount = portfolio_ticker_shares.pop('__CASH', {}).get('shares', 0.0)

    return portfolio_ticker_shares, cash_amount


def main():
    parser = argparse.ArgumentParser(description='Process portfolio data.')
    parser.add_argument('--portfolio_file', type=str, required=True, help=
    'The path to the portfolio JSON file. The file should be in the format: {"TICKER": {"shares": <number>}}, '
    'optionally with the cash amount as "__CASH": {"shares": <number>}')
    parser.add_argument('--llm_prompt_template', type=str, required=True, help=
    f'The path to the LLM prompt template text file that contains {PORTFOLIO_DATA_PLACEHOLDER}.')
    parser.add_argument('--output_prompt', type=str, default=DEFAULT_OUTPUT_PROMPT_FILE, help=
    f'The output file name for the generated LLM prompt. Defaults to "{DEFAULT_OUTPUT_PROMPT_FILE}".')
    args = parser.parse_args()

    portfolio_ticker_shares, cash_amount = load_portfolio_ticker_shares(args.portfolio_file)

    ticker_prices = get_ticker_prices(portfolio_ticker_shares)

    ticker_shares_and_prices = merge_ticker_shares_and_prices(portfolio_ticker_shares, ticker_prices)
    ticker_values_and_weights = calculate_portfolio_1day_diff_and_weight(ticker_shares_and_prices, cash_amount)
    ticker_values_and_weights = add_ticker_names(ticker_values_and_weights)
    print(f"\n--- Portfolio value change from last trading day (top {NUM_TICKERS_TO_PRINT} tickers) ---")
    print(condensed_json(ticker_values_and_weights, NUM_TICKERS_TO_PRINT))

    # Read the prompt template
    with open(args.llm_prompt_template, 'r') as f:
        prompt_template = f.read()

    # Replace the placeholder with the JSON data
    llm_ready_prompt = prompt_template.replace(PORTFOLIO_DATA_PLACEHOLDER,
                                               json.dumps(ticker_values_and_weights, indent=2))

    if args.output_prompt == DEFAULT_OUTPUT_PROMPT_FILE:  # Check if the default output file name is used
        output_file_path = os.path.join(os.path.dirname(args.llm_prompt_template), args.output_prompt)
    else:
        output_file_path = args.output_prompt  # Use the provided path directly
    with open(output_file_path, 'w') as f:
        f.write(llm_ready_prompt)

    print(f"\nLLM prompt written to: {output_file_path}")


def get_ticker_prices(portfolio_ticker_shares: dict) -> dict:
    # The URL of the Cloud Run function
    cloud_run_base_url = os.environ.get("STOCK_QUOTES_CLOUD_RUN_URL")
    if not cloud_run_base_url:
        print("Error: The STOCK_QUOTES_CLOUD_RUN_URL environment variable is not set.", file=sys.stderr)
        print("Please set it to the URL of the stock quotes Cloud Run function.", file=sys.stderr)
        sys.exit(1)
    print(f"Using STOCK_QUOTES_CLOUD_RUN_URL from environment variable: {cloud_run_base_url}")

    tickers = list(portfolio_ticker_shares.keys())
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
        try:
            ticker_prices = json.loads(cloud_run_response)
            print(f"--- Parsed JSON Response (top {NUM_TICKERS_TO_PRINT} tickers) ---")
            print(condensed_json(ticker_prices, NUM_TICKERS_TO_PRINT))
        except json.JSONDecodeError:
            print(f"\nERROR: Cloud Run response is not valid JSON:\n{cloud_run_response}", file=sys.stderr)
            sys.exit(1)


    except Exception as e:
        print(f"\nERROR: Failed to invoke Cloud Run endpoint: {e}. Please check your URL and permissions.",
              file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    # The service returns {"Error": ..., "Symbol": ...} instead of a quote for tickers it failed to fetch
    ticker_errors = {ticker: quote.get('Error') for ticker, quote in ticker_prices.items()
                     if isinstance(quote, dict) and quote.get('Error')}
    if ticker_errors:
        print(f"\nERROR: Cloud Run service {cloud_run_base_url} returned errors instead of quotes for "
              f"{len(ticker_errors)} of {len(tickers)} tickers:", file=sys.stderr)
        for ticker, error in ticker_errors.items():
            print(f"  {ticker}: Error={error}", file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)
    return ticker_prices


def load_sec_json(url: str, cache_file_name: str):
    """
    Returns the parsed JSON at a SEC EDGAR url, cached in SEC_CACHE_DIR as cache_file_name.

    The cached file is used while it's less than 24 hours old (SEC_CACHE_MAX_AGE_SECONDS); after that the url is
    downloaded again and replaces the cached file. If the download fails, an older cached file is used instead.

    Returns:
        The parsed JSON, or None if the download failed and there is no cached file.
    """
    cache_path = os.path.join(SEC_CACHE_DIR, cache_file_name)
    if os.path.exists(cache_path) and time.time() - os.path.getmtime(cache_path) < SEC_CACHE_MAX_AGE_SECONDS:
        with open(cache_path, 'r') as f:
            return json.load(f)

    print(f"Downloading {url} to {cache_path}")
    try:
        user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT)
        response = requests.get(url, headers={"User-Agent": user_agent}, timeout=SEC_REQUEST_TIMEOUT)
        time.sleep(SEC_REQUEST_INTERVAL)
        response.raise_for_status()
        data = response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        if not os.path.exists(cache_path):
            print(f"WARNING: Failed to download {url}: {e}", file=sys.stderr)
            return None
        print(f"WARNING: Failed to download {url}, using the older cached {cache_path}: {e}", file=sys.stderr)
        with open(cache_path, 'r') as f:
            return json.load(f)

    # Write to a temporary file first so another run never reads a partially written cache file
    temp_path = f"{cache_path}.{os.getpid()}.tmp"
    with open(temp_path, 'w') as f:
        json.dump(data, f)
    os.replace(temp_path, cache_path)
    return data


def get_ticker_names(tickers: list) -> dict:
    """
    Looks up the full name of each ticker in SEC EDGAR, e.g.
    {"NVDA": "NVIDIA CORP", "QQQ": "INVESCO QQQ TRUST, SERIES 1"}

    Company tickers are named by their title in company_tickers.json. ETF and mutual fund tickers are only in
    company_tickers_mf.json, which has no names, so they're named by the registrant name in their CIK's submissions.
    A fund's registrant is often a trust of several funds, e.g. VOO is named "VANGUARD INDEX FUNDS".

    Tickers that aren't in SEC EDGAR are left out of the returned dictionary.
    """
    company_tickers = load_sec_json(SEC_COMPANY_TICKERS_URL, "sec_company_tickers.json") or {}
    company_names = {item["ticker"].upper(): item["title"] for item in company_tickers.values()}

    fund_tickers = load_sec_json(SEC_FUND_TICKERS_URL, "sec_company_tickers_mf.json") or {}
    # Each entry is [CIK, Series ID, Class ID, Ticker]
    fund_ciks = {entry[3].upper(): str(entry[0]).zfill(10) for entry in fund_tickers.get("data", [])}

    ticker_names = {}
    for ticker in tickers:
        # SEC tickers separate the share class with '-', e.g. BRK-B for BRK.B
        sec_ticker = ticker.upper().replace('.', '-')
        if sec_ticker in company_names:
            ticker_names[ticker] = company_names[sec_ticker]
        elif sec_ticker in fund_ciks:
            cik = fund_ciks[sec_ticker]
            submissions = load_sec_json(SEC_SUBMISSIONS_URL.format(cik=cik), f"sec_submissions_CIK{cik}.json")
            if submissions and submissions.get("name"):
                ticker_names[ticker] = submissions["name"]
    return ticker_names


def add_ticker_names(ticker_values: dict) -> dict:
    """
    Returns a copy of ticker_values with each ticker's full name from SEC EDGAR as its first attribute, e.g.
    {"NVDA": {"Name": "NVIDIA CORP", "Current Value": 436959.0, "Previous Value": 438549.82, ...}, ...}

    The '__SUM' and '__CASH' entries, and tickers without a name in SEC EDGAR, are copied unchanged.
    """
    tickers = [ticker for ticker in ticker_values if ticker not in ['__SUM', '__CASH']]
    ticker_names = get_ticker_names(tickers)

    unnamed_tickers = [ticker for ticker in tickers if ticker not in ticker_names]
    if unnamed_tickers:
        print(f"WARNING: No SEC EDGAR name found for {len(unnamed_tickers)} tickers: {', '.join(unnamed_tickers)}",
              file=sys.stderr)

    return {ticker: {'Name': ticker_names[ticker], **attributes} if ticker in ticker_names else attributes
            for ticker, attributes in ticker_values.items()}


if __name__ == "__main__":
    main()
