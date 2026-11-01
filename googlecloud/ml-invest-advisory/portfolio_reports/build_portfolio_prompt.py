"""
Builds an LLM prompt from a portfolio's holdings and their real-time stock quotes.

Workflow:
1. Loads the portfolio holdings (tickers and share counts, plus optional cash) from a JSON file.
2. Fetches real-time stock quotes (Last, PreviousClose, ...) from the stock quotes Cloud Run service,
   authenticating with the service account in GOOGLE_APPLICATION_CREDENTIALS.
3. Calculates each holding's current value (shares * Last), previous value (shares * PreviousClose)
   and portfolio weight, plus the portfolio's total values and daily change in percentage.
4. Adds each ticker's full name ("Name") from SEC EDGAR, caching the SEC JSON files next to this
   script for 24 hours.
5. Replaces {{PORTFOLIO_HOLDING_DATA_JSON}} in the LLM prompt template with that data and writes the
   prompt to the output file.

Usage:
    python build_portfolio_prompt.py --portfolio_file <portfolio.json> --llm_prompt_template <template.txt> \
        [--output_prompt <prompt.txt>]

Environment variables:
    GOOGLE_APPLICATION_CREDENTIALS  Path to the service account key file (required).
                                    https://cloud.google.com/docs/authentication/application-default-credentials
    STOCK_QUOTES_CLOUD_RUN_URL      URL of the stock quotes Cloud Run service (required).
    SEC_USER_AGENT                  User-Agent for SEC EDGAR requests: a name and contact email such as
                                    "Agent Identity ai-agent@example.com" (optional, defaults to
                                    DEFAULT_SEC_USER_AGENT).

Exit status:
    0 on success; 1 on a missing environment variable or an invalid quotes response; 69
    (EXIT_CODE_QUOTES_UNAVAILABLE) when the stock quotes are still unavailable after the retries.
"""

import argparse
import json
import os
import sys
import time

import google.auth.transport.requests
import requests
from google.oauth2 import id_token

# --- Portfolio JSON and LLM prompt ---
# Keys of the portfolio totals and of the cash holding in the portfolio file and in the prompt data.
SUM_KEY = "__SUM"
CASH_KEY = "__CASH"
PORTFOLIO_DATA_PLACEHOLDER = "{{PORTFOLIO_HOLDING_DATA_JSON}}"
# Without --output_prompt, the prompt is written to this file next to the prompt template.
DEFAULT_OUTPUT_PROMPT_FILE = "prompt.txt"
# Number of tickers printed to the terminal from the quotes and from the portfolio values.
NUM_TICKERS_TO_PRINT = 3

# --- Stock quotes Cloud Run service ---
# Seconds to wait before each retry of a failed request: exponential backoff up to 16 seconds, then give up
# (6 attempts over ~31 seconds of waiting).
CLOUD_RUN_RETRY_DELAYS = [1, 2, 4, 8, 16]
CLOUD_RUN_REQUEST_TIMEOUT = 60
# Exit code when the stock quotes are still unavailable after all retries (sysexits EX_UNAVAILABLE).
# scripts/run-market-hours.sh reports this exit code as a quotes endpoint failure.
EXIT_CODE_QUOTES_UNAVAILABLE = 69

# --- SEC EDGAR ticker names ---
# Company tickers (NVDA) have a title; ETF and mutual fund tickers (QQQ) only have a CIK, whose submissions have
# the registrant name.
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


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

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


def describe_request_failure(error: requests.exceptions.RequestException) -> str:
    """
    Describes a failed request for the terminal: the error and, if the server responded, its status code and body.

    The stock quotes Cloud Run function returns upstream errors in the body, e.g. a 500 with
    {"error": "... returned 403 for url: ...", "detail": "<html>...403 Forbidden...</html>"},
    so the body is what explains the failure. JSON bodies are pretty-printed.
    """
    if error.response is None:
        return str(error)
    try:
        body = json.dumps(error.response.json(), indent=2)
    except ValueError:
        body = error.response.text
    return f"{error}\nResponse status: {error.response.status_code}\nResponse body:\n{body}"


# ---------------------------------------------------------------------------
# Portfolio file
# ---------------------------------------------------------------------------

def load_portfolio(file_path: str) -> tuple[dict, float]:
    """
    Loads the share counts and the cash amount from a portfolio JSON file, e.g.:
    {
      "NVDA": {"shares": 2050.0},
      "BIL": {"shares": 634.0},
      "__CASH": {"shares": 492.08}
    }

    Returns:
        tuple: The share counts by ticker (without CASH_KEY), and the cash amount (0.0 without CASH_KEY).
    """
    with open(file_path, 'r') as f:
        shares_by_ticker = json.load(f)

    cash_amount = shares_by_ticker.pop(CASH_KEY, {}).get('shares', 0.0)
    return shares_by_ticker, cash_amount


# ---------------------------------------------------------------------------
# Stock quotes
# ---------------------------------------------------------------------------

def get_cloud_run_response(audience: str, url: str) -> str:
    """
    Sends an authenticated GET request to a Cloud Run endpoint and returns the response text.

    The request carries an ID token for the service account in GOOGLE_APPLICATION_CREDENTIALS. The token's audience
    is the endpoint's base URL (as shown in the Google Cloud console), so the token is only valid for that service.
    A failed request is retried after each delay in CLOUD_RUN_RETRY_DELAYS (1, 2, 4, 8, 16 seconds).

    Args:
        audience (str): The base URL of the Cloud Run endpoint.
        url (str): The full URL to request, including the query string.

    Raises:
        Exception: If the ID token can't be fetched or the request still fails after the last retry.
    """
    try:
        print(f"Authenticating for audience: {audience}")
        identity_token = id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)
        headers = {"Authorization": f"Bearer {identity_token}"}
        print(f"Successfully obtained ID token. Making request at {url}")

        # Retry failures with exponential backoff so a failing endpoint isn't called in a tight loop.
        for attempt, retry_delay in enumerate(CLOUD_RUN_RETRY_DELAYS + [None], start=1):
            try:
                response = requests.get(url, headers=headers, timeout=CLOUD_RUN_REQUEST_TIMEOUT)
                response.raise_for_status()  # 4xx and 5xx responses raise an exception
                return response.text
            except requests.exceptions.RequestException as error:
                next_step = f"retrying in {retry_delay}s" if retry_delay is not None else \
                    f"giving up after {len(CLOUD_RUN_RETRY_DELAYS)} retries"
                print(f"ERROR: Cloud Run request attempt {attempt} failed, {next_step}: "
                      f"{describe_request_failure(error)}", file=sys.stderr, flush=True)
                if retry_delay is None:
                    raise
                time.sleep(retry_delay)

    except Exception as error:
        print(f"An error occurred: {error}", file=sys.stderr)
        raise


def fetch_stock_quotes(tickers: list) -> dict:
    """
    Fetches the stock quotes of the tickers from STOCK_QUOTES_CLOUD_RUN_URL.

    Returns:
        dict: The quote of each ticker, e.g. {"NVDA": {"Last": 183.16, "PreviousClose": 192.1, ...}, ...}.
        Exits with status 1 when an environment variable is missing or the response isn't JSON, and with
        EXIT_CODE_QUOTES_UNAVAILABLE when the service can't be reached or returns errors instead of quotes.
    """
    quotes_base_url = os.environ.get("STOCK_QUOTES_CLOUD_RUN_URL")
    if not quotes_base_url:
        print("Error: The STOCK_QUOTES_CLOUD_RUN_URL environment variable is not set.", file=sys.stderr)
        print("Please set it to the URL of the stock quotes Cloud Run function.", file=sys.stderr)
        sys.exit(1)
    print(f"Using STOCK_QUOTES_CLOUD_RUN_URL from environment variable: {quotes_base_url}")

    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
        print("Error: The GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.", file=sys.stderr)
        print("Please set it to the path of your service account key file.", file=sys.stderr)
        sys.exit(1)

    quotes_url = f"{quotes_base_url}/?tickers={','.join(tickers)}"
    try:
        response_text = get_cloud_run_response(quotes_base_url, quotes_url)
    except Exception as error:
        print(f"\nERROR: Failed to invoke Cloud Run endpoint: {error}. Please check your URL and permissions.",
              file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    print("\n--- Parsing response from Cloud Run service to JSON ---")
    try:
        quotes = json.loads(response_text)
    except json.JSONDecodeError:
        print(f"\nERROR: Cloud Run response is not valid JSON:\n{response_text}", file=sys.stderr)
        sys.exit(1)
    print(f"--- Parsed JSON Response (top {NUM_TICKERS_TO_PRINT} tickers) ---")
    print(condensed_json(quotes, NUM_TICKERS_TO_PRINT))

    # The service returns {"Error": ..., "Symbol": ...} instead of a quote for tickers it failed to fetch.
    errors_by_ticker = {ticker: quote.get('Error') for ticker, quote in quotes.items()
                        if isinstance(quote, dict) and quote.get('Error')}
    if errors_by_ticker:
        print(f"\nERROR: Cloud Run service {quotes_base_url} returned errors instead of quotes for "
              f"{len(errors_by_ticker)} of {len(tickers)} tickers:", file=sys.stderr)
        for ticker, error in errors_by_ticker.items():
            print(f"  {ticker}: Error={error}", file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)
    return quotes


# ---------------------------------------------------------------------------
# Portfolio values and weights
# ---------------------------------------------------------------------------

def merge_shares_into_quotes(shares_by_ticker: dict, quotes: dict) -> dict:
    """
    Returns a copy of the quotes with each ticker's share count added to its quote.

    Args:
        shares_by_ticker (dict): The share count of each ticker, e.g. {"AAAU": {"shares": 31.90}, "NVDA": {"shares": 1}}.
        quotes (dict): The quote of each ticker. Prices, sizes and volumes are JSON numbers
            (calculate_values_and_weights also accepts numeric strings), e.g.:
            {
              "AAAU": {"Ask": 40.45, "AskSize": 100.0, "Bid": 38.07, "BidSize": 100.0, "Close": 39.41, "High": 39.68,
                       "Last": 39.41, "LastSize": 200.0, "LastVenue": "V", "Low": 39.18, "NetChange": -0.265,
                       "NetChangePct": -0.6679269061121628, "Open": 39.67, "PreviousClose": 39.675,
                       "PreviousVolume": 42632.0, "Symbol": "AAAU", "TradeTime": "2026-10-23T19:59:38Z",
                       "VWAP": 39.383618, "Volume": 45000.0}
            }
            NetChangePct is a percentage, e.g. -0.67 means -0.67%.

    A ticker without a quote keeps only its share count, which calculate_values_and_weights reports as an error.
    """
    merged = json.loads(json.dumps(quotes))  # deep copy, so the quotes aren't changed
    for ticker, share_attributes in shares_by_ticker.items():
        if ticker in merged:
            merged[ticker].update(share_attributes)
        else:
            merged[ticker] = share_attributes
    return merged


def calculate_values_and_weights(quotes_with_shares: dict, cash_amount: float = 0) -> dict:
    """
    Calculates each holding's values and weight, plus the portfolio totals, with attribute names an LLM understands.

    Args:
        quotes_with_shares (dict): The quote of each ticker with its "shares", "Last" and "PreviousClose"
            (numbers or numeric strings), as returned by merge_shares_into_quotes.
        cash_amount (float): The cash in the portfolio, added to the totals and weighted like a holding.

    Returns:
        dict: For each ticker, its "Current Value", "Previous Value", "shares", "single share change in percentage"
        and "weight in percentage"; then SUM_KEY with the totals and "daily performance change in percentage", and
        CASH_KEY with the cash amount and its weight. Exits with EXIT_CODE_QUOTES_UNAVAILABLE if any ticker lacks a
        usable quote, since the weights and totals would be wrong.
    """
    values_by_ticker = {}
    total_current_value = 0.0
    total_previous_value = 0.0
    failed_tickers = []

    for ticker, attributes in quotes_with_shares.items():
        try:
            for required in ('shares', 'Last', 'PreviousClose'):
                if attributes.get(required) is None:
                    raise ValueError(f"'{required}' attribute missing; the stock quotes response has no "
                                     f"usable quote for this ticker")
            shares = float(attributes.get('shares'))
            current_value = shares * float(attributes.get('Last'))
            previous_value = shares * float(attributes.get('PreviousClose'))

            values_by_ticker[ticker] = {
                'Current Value': round(current_value, 2),
                'Previous Value': round(previous_value, 2),
                'shares': shares,
                'single share change in percentage': f"{float(attributes.get('NetChangePct', 0)):.2f}%",
            }
            total_current_value += current_value
            total_previous_value += previous_value

        except (ValueError, TypeError) as error:
            print(f"ERROR: ticker {ticker} has a data error: {error}", file=sys.stderr)
            failed_tickers.append(ticker)

    if failed_tickers:
        print(f"\nERROR: Cannot calculate portfolio values; missing or invalid quotes for "
              f"{len(failed_tickers)} tickers: {', '.join(failed_tickers)}", file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    total_current_value += cash_amount
    total_previous_value += cash_amount
    daily_change_percent = (total_current_value - total_previous_value) / total_previous_value * 100
    values_by_ticker[SUM_KEY] = {
        'Current Value': round(total_current_value, 2),
        'Previous Value': round(total_previous_value, 2),
        'daily performance change in percentage': str(round(daily_change_percent, 2)) + '%'
    }
    portfolio_value = values_by_ticker[SUM_KEY]['Current Value']
    values_by_ticker[CASH_KEY] = {
        'shares': cash_amount,
        'weight in percentage': str(round(cash_amount / portfolio_value * 100, 2)) + '%'
    }

    for ticker, attributes in values_by_ticker.items():
        if ticker not in (SUM_KEY, CASH_KEY):
            attributes['weight in percentage'] = str(round(attributes['Current Value'] / portfolio_value * 100, 2)) + '%'

    return values_by_ticker


# ---------------------------------------------------------------------------
# SEC EDGAR ticker names
# ---------------------------------------------------------------------------

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
    except (requests.exceptions.RequestException, ValueError) as error:
        if not os.path.exists(cache_path):
            print(f"WARNING: Failed to download {url}: {error}", file=sys.stderr)
            return None
        print(f"WARNING: Failed to download {url}, using the older cached {cache_path}: {error}", file=sys.stderr)
        with open(cache_path, 'r') as f:
            return json.load(f)

    # Write to a temporary file first so another run never reads a partially written cache file.
    temp_path = f"{cache_path}.{os.getpid()}.tmp"
    with open(temp_path, 'w') as f:
        json.dump(data, f)
    os.replace(temp_path, cache_path)
    return data


def lookup_ticker_names(tickers: list) -> dict:
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

    names_by_ticker = {}
    for ticker in tickers:
        # SEC tickers separate the share class with '-', e.g. BRK-B for BRK.B
        sec_ticker = ticker.upper().replace('.', '-')
        if sec_ticker in company_names:
            names_by_ticker[ticker] = company_names[sec_ticker]
        elif sec_ticker in fund_ciks:
            cik = fund_ciks[sec_ticker]
            submissions = load_sec_json(SEC_SUBMISSIONS_URL.format(cik=cik), f"sec_submissions_CIK{cik}.json")
            if submissions and submissions.get("name"):
                names_by_ticker[ticker] = submissions["name"]
    return names_by_ticker


def add_ticker_names(values_by_ticker: dict) -> dict:
    """
    Returns a copy of values_by_ticker with each ticker's full name from SEC EDGAR as its first attribute, e.g.
    {"NVDA": {"Name": "NVIDIA CORP", "Current Value": 436959.0, "Previous Value": 438549.82, ...}, ...}

    The SUM_KEY and CASH_KEY entries, and tickers without a name in SEC EDGAR, are copied unchanged.
    """
    tickers = [ticker for ticker in values_by_ticker if ticker not in (SUM_KEY, CASH_KEY)]
    names_by_ticker = lookup_ticker_names(tickers)

    unnamed_tickers = [ticker for ticker in tickers if ticker not in names_by_ticker]
    if unnamed_tickers:
        print(f"WARNING: No SEC EDGAR name found for {len(unnamed_tickers)} tickers: {', '.join(unnamed_tickers)}",
              file=sys.stderr)

    return {ticker: {'Name': names_by_ticker[ticker], **attributes} if ticker in names_by_ticker else attributes
            for ticker, attributes in values_by_ticker.items()}


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

def write_prompt(template_path: str, portfolio_data: dict, output_path: str) -> None:
    """Writes the prompt template to output_path with PORTFOLIO_DATA_PLACEHOLDER replaced by portfolio_data."""
    with open(template_path, 'r') as f:
        template = f.read()
    prompt = template.replace(PORTFOLIO_DATA_PLACEHOLDER, json.dumps(portfolio_data, indent=2))
    with open(output_path, 'w') as f:
        f.write(prompt)
    print(f"\nLLM prompt written to: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Builds an LLM prompt from a portfolio and its real-time quotes.')
    parser.add_argument('--portfolio_file', type=str, required=True, help=
    'The path to the portfolio JSON file. The file should be in the format: {"TICKER": {"shares": <number>}}, '
    f'optionally with the cash amount as "{CASH_KEY}": {{"shares": <number>}}')
    parser.add_argument('--llm_prompt_template', type=str, required=True, help=
    f'The path to the LLM prompt template text file that contains {PORTFOLIO_DATA_PLACEHOLDER}.')
    parser.add_argument('--output_prompt', type=str, default=DEFAULT_OUTPUT_PROMPT_FILE, help=
    f'The output file name for the generated LLM prompt. Defaults to "{DEFAULT_OUTPUT_PROMPT_FILE}" '
    f'next to the prompt template.')
    return parser.parse_args()


def main():
    args = parse_args()

    shares_by_ticker, cash_amount = load_portfolio(args.portfolio_file)
    quotes = fetch_stock_quotes(list(shares_by_ticker.keys()))

    quotes_with_shares = merge_shares_into_quotes(shares_by_ticker, quotes)
    portfolio_data = add_ticker_names(calculate_values_and_weights(quotes_with_shares, cash_amount))
    print(f"\n--- Portfolio value change from last trading day (top {NUM_TICKERS_TO_PRINT} tickers) ---")
    print(condensed_json(portfolio_data, NUM_TICKERS_TO_PRINT))

    if args.output_prompt == DEFAULT_OUTPUT_PROMPT_FILE:
        output_path = os.path.join(os.path.dirname(args.llm_prompt_template), args.output_prompt)
    else:
        output_path = args.output_prompt
    write_prompt(args.llm_prompt_template, portfolio_data, output_path)


if __name__ == "__main__":
    main()
