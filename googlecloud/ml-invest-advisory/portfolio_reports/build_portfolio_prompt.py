"""
Builds an LLM prompt from a portfolio's holdings and their real-time stock quotes.

Workflow:
1. Loads the portfolio holdings (tickers and share counts, plus optional cash) from a JSON file.
2. Fetches real-time stock quotes ("price", "previous-close", ...) from the stock quotes Cloud Run services,
   authenticating with the service account in GOOGLE_APPLICATION_CREDENTIALS: US tickers such as "VOO" from
   STOCK_QUOTES_CLOUD_RUN_URL, and Taiwan tickers with the "TW:" prefix such as "TW:2330" from
   TW_STOCK_QUOTES_CLOUD_RUN_URL.
3. Converts quotes in other currencies, e.g. TWD for Taiwan tickers, to USD with the day's exchange rate from
   USD_EXCHANGE_RATES_URL.
4. Calculates each holding's current value (shares * price), previous value (shares * previous-close)
   and portfolio weight, plus the portfolio's total values and daily change in percentage, all in USD.
5. Adds each ticker's name ("Name"): from the ticker names file (--ticker_names_file, by default
   ticker_names.json next to this script) if the ticker is in it, otherwise from SEC EDGAR for US tickers, caching the
   SEC JSON files next to this script for 24 hours. The ticker names file names ETFs by fund and holdings,
   e.g. "iShares MSCI Taiwan ETF (Taiwanese stocks)", where SEC EDGAR only has the issuing trust
   ("iShares, Inc.").
6. Replaces {{PORTFOLIO_HOLDING_DATA_JSON}} in the LLM prompt template with that data and writes the
   prompt to the output file.

Usage:
    python build_portfolio_prompt.py --portfolio_file <portfolio.json> --llm_prompt_template <template.txt> \
        [--output_prompt <prompt.txt>] [--ticker_names_file <ticker_names.json>]

Environment variables:
    GOOGLE_APPLICATION_CREDENTIALS  Path to the service account key file (required).
                                    https://cloud.google.com/docs/authentication/application-default-credentials
    STOCK_QUOTES_CLOUD_RUN_URL      URL of the get-us-ticker-quotes Cloud Run service (required when the
                                    portfolio has US tickers).
    TW_STOCK_QUOTES_CLOUD_RUN_URL   URL of the get-tw-ticker-quotes Cloud Run service (required when the
                                    portfolio has "TW:" tickers).
    SEC_USER_AGENT                  User-Agent for SEC EDGAR requests: a name and contact email such as
                                    "Agent Identity ai-agent@example.com" (optional, defaults to
                                    DEFAULT_SEC_USER_AGENT).

Exit status:
    0 on success; 1 on a missing environment variable or an invalid quotes response; 69
    (EXIT_CODE_QUOTES_UNAVAILABLE) when the stock quotes or exchange rates are still unavailable after the retries.
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

# --- Stock quotes Cloud Run services ---
# Portfolio tickers with this prefix, e.g. "TW:2330", are Taiwan stocks quoted by TW_STOCK_QUOTES_CLOUD_RUN_URL;
# other tickers are US stocks quoted by STOCK_QUOTES_CLOUD_RUN_URL.
TW_TICKER_PREFIX = "TW:"
# Seconds to wait before each retry of a failed request: exponential backoff up to 16 seconds, then give up
# (6 attempts over ~31 seconds of waiting).
CLOUD_RUN_RETRY_DELAYS = [1, 2, 4, 8, 16]
CLOUD_RUN_REQUEST_TIMEOUT = 60
# Exit code when the stock quotes are still unavailable after all retries (sysexits EX_UNAVAILABLE).
# scripts/run-market-hours.sh reports this exit code as a quotes endpoint failure.
EXIT_CODE_QUOTES_UNAVAILABLE = 69

# --- Exchange rates ---
# ExchangeRate-API's open access endpoint: free and without an API key, updated once a day, and asks for the
# attribution "Rates By Exchange Rate API" (https://www.exchangerate-api.com). https://www.exchangerate-api.com/docs/free
USD_EXCHANGE_RATES_URL = "https://open.er-api.com/v6/latest/USD"
EXCHANGE_RATES_REQUEST_TIMEOUT = 30
# Price fields of a quote converted to USD; net-change-% is a ratio and stays as is.
QUOTE_PRICE_FIELDS = ('price', 'previous-close', 'net-change', 'open', 'high', 'low', 'close', 'bid', 'ask')

# --- Ticker names ---
# Ticker names file: {"TICKER": "Name", ...}, used before SEC EDGAR. Without --ticker_names_file, this file next to
# this script is used.
DEFAULT_TICKER_NAMES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticker_names.json")
# SEC EDGAR: company tickers (NVDA) have a title; ETF and mutual fund tickers (QQQ) only have a CIK, whose
# submissions have the registrant name.
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
    {"error": "Alpaca API returned 403", "detail": "<Alpaca's response body>"}, so the body is what explains the
    failure. JSON bodies are pretty-printed, e.g.:

        500 Server Error: Internal Server Error for url: https://.../get-us-ticker-quotes/?tickers=VOO
        Response status: 500
        Response body:
        {
          "error": "Alpaca API returned 403",
          "detail": "{\"message\": \"forbidden.\"}"
        }

    Without a response, e.g. on a timeout or a DNS failure, only the error is returned.
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
        tuple: The share counts by ticker (without CASH_KEY), and the cash amount (0.0 without CASH_KEY), e.g. for
        the file above: ({"NVDA": {"shares": 2050.0}, "BIL": {"shares": 634.0}}, 492.08)
    """
    with open(file_path, 'r') as f:
        shares_by_ticker = json.load(f)

    cash_amount = shares_by_ticker.pop(CASH_KEY, {}).get('shares', 0.0)
    return shares_by_ticker, cash_amount


# ---------------------------------------------------------------------------
# Stock quotes
# ---------------------------------------------------------------------------

def get_with_retries(url: str, headers: dict = None, timeout: int = CLOUD_RUN_REQUEST_TIMEOUT) -> requests.Response:
    """
    Sends a GET request and returns the successful response, retrying a failure after each delay in
    CLOUD_RUN_RETRY_DELAYS (1, 2, 4, 8, 16 seconds) so a failing endpoint isn't called in a tight loop.

    Args:
        url (str): The URL to request, e.g. USD_EXCHANGE_RATES_URL.
        headers (dict): Request headers, e.g. {"Authorization": "Bearer <ID token>"}.
        timeout (int): Seconds to wait for each attempt.

    Returns:
        requests.Response: The first 2xx response.

    Raises:
        requests.exceptions.RequestException: If the last retry still fails, e.g. a 500 or a timeout. Each failure
            is printed to stderr with describe_request_failure.
    """
    for attempt, retry_delay in enumerate(CLOUD_RUN_RETRY_DELAYS + [None], start=1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()  # 4xx and 5xx responses raise an exception
            return response
        except requests.exceptions.RequestException as error:
            next_step = f"retrying in {retry_delay}s" if retry_delay is not None else \
                f"giving up after {len(CLOUD_RUN_RETRY_DELAYS)} retries"
            print(f"ERROR: Request attempt {attempt} to {url} failed, {next_step}: "
                  f"{describe_request_failure(error)}", file=sys.stderr, flush=True)
            if retry_delay is None:
                raise
            time.sleep(retry_delay)


def get_cloud_run_response(audience: str, url: str) -> str:
    """
    Sends an authenticated GET request to a Cloud Run endpoint and returns the response text.

    The request carries an ID token for the service account in GOOGLE_APPLICATION_CREDENTIALS. The token's audience
    is the endpoint's base URL (as shown in the Google Cloud console), so the token is only valid for that service.
    A failed request is retried by get_with_retries.

    Args:
        audience (str): The base URL of the Cloud Run endpoint,
            e.g. "https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes".
        url (str): The full URL to request, including the query string,
            e.g. "https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes/?tickers=VOO,QQQ".

    Returns:
        str: The response body, e.g. '{"QQQ": {"symbol": "QQQ", ...}, "VOO": {"symbol": "VOO", "price": 675.9, ...}}'.

    Raises:
        Exception: If the ID token can't be fetched or the request still fails after the last retry.
    """
    try:
        print(f"Authenticating for audience: {audience}")
        identity_token = id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)
        print(f"Successfully obtained ID token. Making request at {url}")
        return get_with_retries(url, headers={"Authorization": f"Bearer {identity_token}"}).text
    except Exception as error:
        print(f"An error occurred: {error}", file=sys.stderr)
        raise


def fetch_quotes_from_service(url_variable: str, symbols: list) -> dict:
    """
    Fetches the quotes of the symbols from the stock quotes Cloud Run service at the URL in environment variable
    url_variable.

    Args:
        url_variable (str): "STOCK_QUOTES_CLOUD_RUN_URL" or "TW_STOCK_QUOTES_CLOUD_RUN_URL".
        symbols (list): Symbols without a market prefix, e.g. ["VOO", "XYZQ"] or ["2330", "006208"], requested as
            $<url_variable>/?tickers=VOO,XYZQ.

    Returns:
        dict: The service's response body, the quote of each symbol it could quote, e.g.
        {"VOO": {"symbol": "VOO", "price": 675.9, "previous-close": 673.94, ...}}. Symbols the service can't quote,
        like XYZQ, are left out (the service lists them in its X-Alpaca-Errors or X-SinoTrade-Errors response header);
        calculate_values_and_weights reports them.
        Exits with status 1 when an environment variable is missing or the response isn't JSON, and with
        EXIT_CODE_QUOTES_UNAVAILABLE when the service can't be reached.
    """
    quotes_base_url = os.environ.get(url_variable)
    if not quotes_base_url:
        print(f"Error: The {url_variable} environment variable is not set.", file=sys.stderr)
        print("Please set it to the URL of the stock quotes Cloud Run function.", file=sys.stderr)
        sys.exit(1)
    print(f"Using {url_variable} from environment variable: {quotes_base_url}")

    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
        print("Error: The GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.", file=sys.stderr)
        print("Please set it to the path of your service account key file.", file=sys.stderr)
        sys.exit(1)

    quotes_url = f"{quotes_base_url}/?tickers={','.join(symbols)}"
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

    return quotes


def fetch_stock_quotes(tickers: list) -> dict:
    """
    Fetches the stock quotes of the portfolio's tickers: US tickers from STOCK_QUOTES_CLOUD_RUN_URL and Taiwan
    tickers, those with TW_TICKER_PREFIX, from TW_STOCK_QUOTES_CLOUD_RUN_URL. A market's service is only called when
    the portfolio has tickers in that market.

    Args:
        tickers (list): Portfolio tickers, e.g. ["VOO", "TW:2330", "XYZQ"].

    Returns:
        dict: The quote of each ticker, keyed like the portfolio, e.g. after the close on 2026-11-06:
        {
          "VOO": {"symbol": "VOO", "price": 675.9, "previous-close": 673.94, "net-change": 1.96, "net-change-%": 0.29,
                  "trade-time": "2026-11-06T21:00:03Z", "open": 675.435, "high": 681.44, "low": 675.34,
                  "close": 676.02, "volume": 109275.0, "bid": 655.12, "ask": 696.49},
          "TW:2330": {"symbol": "2330", "price": 2135.0, "previous-close": 2240.0, "net-change": -105.0,
                      "net-change-%": -4.68, "trade-time": "2026-11-06T06:30:00Z", "open": 2020.0, "high": 2195.0,
                      "low": 2020.0, "bid": 2135.0, "ask": 2140.0, "currency": "TWD"}
        }
        Quotes without "currency" are in USD. Tickers a service can't quote, like XYZQ, are left out. Exits like
        fetch_quotes_from_service.
    """
    us_tickers = [ticker for ticker in tickers if not ticker.startswith(TW_TICKER_PREFIX)]
    tw_symbols = [ticker.removeprefix(TW_TICKER_PREFIX) for ticker in tickers if ticker.startswith(TW_TICKER_PREFIX)]

    quotes = {}
    if us_tickers:
        quotes.update(fetch_quotes_from_service("STOCK_QUOTES_CLOUD_RUN_URL", us_tickers))
    if tw_symbols:
        tw_quotes = fetch_quotes_from_service("TW_STOCK_QUOTES_CLOUD_RUN_URL", tw_symbols)
        quotes.update({f"{TW_TICKER_PREFIX}{symbol}": quote for symbol, quote in tw_quotes.items()})
    return quotes


# ---------------------------------------------------------------------------
# Exchange rates
# ---------------------------------------------------------------------------

def fetch_local_currency_per_usd(currencies: set) -> dict:
    """
    Fetches how many units of each currency one US dollar buys, from USD_EXCHANGE_RATES_URL (updated once a day).

    Args:
        currencies (set): ISO 4217 currency codes, e.g. {"TWD"}.

    Returns:
        dict: The rate of each currency, e.g. {"TWD": 32.847015} on 2026-11-08. Exits with
        EXIT_CODE_QUOTES_UNAVAILABLE if the rates can't be fetched after the retries, the response isn't valid, or a
        currency has no rate, since the USD values would be wrong.
    """
    try:
        response = get_with_retries(USD_EXCHANGE_RATES_URL, timeout=EXCHANGE_RATES_REQUEST_TIMEOUT)
        exchange_rates = response.json()
        rates = exchange_rates['rates']
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as error:
        print(f"\nERROR: Failed to fetch exchange rates from {USD_EXCHANGE_RATES_URL}: {error}", file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    missing_currencies = sorted(currency for currency in currencies if not rates.get(currency))
    if missing_currencies:
        print(f"\nERROR: {USD_EXCHANGE_RATES_URL} has no exchange rate for {', '.join(missing_currencies)}",
              file=sys.stderr)
        sys.exit(EXIT_CODE_QUOTES_UNAVAILABLE)

    local_per_usd = {currency: float(rates[currency]) for currency in currencies}
    print(f"Exchange rates (Rates By Exchange Rate API, updated {exchange_rates.get('time_last_update_utc')}): " +
          ', '.join(f"1 USD = {rate} {currency}" for currency, rate in sorted(local_per_usd.items())))
    return local_per_usd


def convert_quotes_to_usd(quotes: dict, local_per_usd: dict) -> dict:
    """
    Returns a copy of the quotes with the QUOTE_PRICE_FIELDS of quotes in another currency divided by its rate, and
    their "currency" set to "USD". Quotes without "currency" or in USD are copied unchanged.

    Both the price and the previous close are converted with the current rate, so a holding's daily change in USD
    leaves out the exchange rate's own change since the previous close.

    Args:
        quotes (dict): The quote of each ticker, as returned by fetch_stock_quotes, e.g.
            {"TW:2330": {"price": 2135.0, "previous-close": 2240.0, "net-change-%": -4.68, "currency": "TWD"}}.
        local_per_usd (dict): Units of each currency per US dollar, e.g. {"TWD": 32.847015}.

    Returns:
        dict: The quotes in USD, e.g.
        {"TW:2330": {"price": 64.9983..., "previous-close": 68.1949..., "net-change-%": -4.68, "currency": "USD"}}.
    """
    converted = {}
    for ticker, quote in quotes.items():
        currency = quote.get('currency', 'USD')
        if currency == 'USD':
            converted[ticker] = dict(quote)
            continue
        rate = local_per_usd[currency]
        converted[ticker] = {**quote, 'currency': 'USD',
                             **{field: float(quote[field]) / rate for field in QUOTE_PRICE_FIELDS
                                if quote.get(field) is not None}}
    return converted


def quotes_in_usd(quotes: dict) -> dict:
    """
    Returns the quotes converted to USD by convert_quotes_to_usd, fetching exchange rates only when a quote is in
    another currency, e.g. for a portfolio with "TW:" tickers.
    """
    currencies = {quote.get('currency', 'USD') for quote in quotes.values() if isinstance(quote, dict)} - {'USD'}
    if not currencies:
        return quotes
    return convert_quotes_to_usd(quotes, fetch_local_currency_per_usd(currencies))


# ---------------------------------------------------------------------------
# Portfolio values and weights
# ---------------------------------------------------------------------------

def merge_shares_into_quotes(shares_by_ticker: dict, quotes: dict) -> dict:
    """
    Returns a copy of the quotes with each ticker's share count added to its quote.

    Args:
        shares_by_ticker (dict): The share count of each ticker, e.g. {"AAAU": {"shares": 31.90}, "NVDA": {"shares": 1}}.
        quotes (dict): The quote of each ticker from the get-us-ticker-quotes function. Prices and volumes are
            JSON numbers (calculate_values_and_weights also accepts numeric strings), e.g.:
            {
              "AAAU": {"symbol": "AAAU", "price": 39.41, "previous-close": 39.675, "net-change": -0.265,
                       "net-change-%": -0.67, "trade-time": "2026-10-23T19:59:38Z", "open": 39.67, "high": 39.68,
                       "low": 39.18, "close": 39.41, "volume": 45000.0, "bid": 38.07, "ask": 40.45}
            }
            net-change-% is a percentage, e.g. -0.67 means -0.67%.

    Returns:
        dict: The quotes with the share counts added, e.g. for shares_by_ticker
        {"AAAU": {"shares": 10}, "XYZQ": {"shares": 1}} and the quotes above:
        {
          "AAAU": {"symbol": "AAAU", "price": 39.41, "previous-close": 39.675, ..., "ask": 40.45, "shares": 10},
          "XYZQ": {"shares": 1}
        }
        A ticker without a quote, like XYZQ, keeps only its share count, which calculate_values_and_weights reports
        as an error. The quotes argument isn't changed.
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
        quotes_with_shares (dict): The quote of each ticker with its "shares", "price" and "previous-close"
            (numbers or numeric strings), as returned by merge_shares_into_quotes.
        cash_amount (float): The cash in the portfolio, added to the totals and weighted like a holding.

    Returns:
        dict: For each ticker, its "Current Value", "Previous Value", "shares", "single share change in percentage"
        and "weight in percentage"; then SUM_KEY with the totals and "daily performance change in percentage", and
        CASH_KEY with the cash amount and its weight. Exits with EXIT_CODE_QUOTES_UNAVAILABLE if any ticker lacks a
        usable quote, since the weights and totals would be wrong.

    Example, for VOO and AAAU after the close on 2026-11-06 and 100.0 in cash:
        quotes_with_shares = {
          "VOO": {"price": 675.9, "previous-close": 673.94, "net-change-%": 0.29, "shares": 2},
          "AAAU": {"price": 39.41, "previous-close": 39.675, "net-change-%": -0.67, "shares": 10}
        }
        returns:
        {
          "VOO": {"Current Value": 1351.8, "Previous Value": 1347.88, "shares": 2.0,
                  "single share change in percentage": "0.29%", "weight in percentage": "73.23%"},
          "AAAU": {"Current Value": 394.1, "Previous Value": 396.75, "shares": 10.0,
                   "single share change in percentage": "-0.67%", "weight in percentage": "21.35%"},
          "__SUM": {"Current Value": 1845.9, "Previous Value": 1844.63,
                    "daily performance change in percentage": "0.07%"},
          "__CASH": {"shares": 100.0, "weight in percentage": "5.42%"}
        }
    """
    values_by_ticker = {}
    total_current_value = 0.0
    total_previous_value = 0.0
    failed_tickers = []

    for ticker, attributes in quotes_with_shares.items():
        try:
            for required in ('shares', 'price', 'previous-close'):
                if attributes.get(required) is None:
                    raise ValueError(f"'{required}' attribute missing; the stock quotes response has no "
                                     f"usable quote for this ticker")
            shares = float(attributes.get('shares'))
            current_value = shares * float(attributes.get('price'))
            previous_value = shares * float(attributes.get('previous-close'))

            values_by_ticker[ticker] = {
                'Current Value': round(current_value, 2),
                'Previous Value': round(previous_value, 2),
                'shares': shares,
                'single share change in percentage': f"{float(attributes.get('net-change-%', 0)):.2f}%",
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
# Ticker names: ticker names file, then SEC EDGAR
# ---------------------------------------------------------------------------

def load_ticker_names_file(file_path: str) -> dict:
    """
    Loads the names of tickers from a ticker names file, e.g.:
    {
      "EWT": "iShares MSCI Taiwan ETF (Taiwanese stocks)",
      "QQQ": "Invesco QQQ Trust (Nasdaq-100)"
    }

    Returns:
        dict: The name of each ticker, with upper-case tickers and surrounding spaces removed from the names; the
        file above is returned as is. Empty if the file is missing or invalid, after a warning, so the names come
        from SEC EDGAR instead of a typo in the file stopping the reports.
    """
    if not os.path.exists(file_path):
        print(f"WARNING: Ticker names file {file_path} not found; using SEC EDGAR names only", file=sys.stderr)
        return {}
    try:
        with open(file_path, 'r') as f:
            names_by_ticker = json.load(f)
        if not isinstance(names_by_ticker, dict) or \
                not all(isinstance(name, str) and name.strip() for name in names_by_ticker.values()):
            raise ValueError('expected {"TICKER": "Name", ...} with a non-empty name for every ticker')
    except ValueError as error:  # json.JSONDecodeError is a ValueError
        print(f"WARNING: Ignoring invalid ticker names file {file_path}: {error}; using SEC EDGAR names only",
              file=sys.stderr)
        return {}
    return {ticker.upper(): name.strip() for ticker, name in names_by_ticker.items()}


def load_sec_json(url: str, cache_file_name: str):
    """
    Returns the parsed JSON at a SEC EDGAR url, cached in SEC_CACHE_DIR as cache_file_name.

    The cached file is used while it's less than 24 hours old (SEC_CACHE_MAX_AGE_SECONDS); after that the url is
    downloaded again and replaces the cached file. If the download fails, an older cached file is used instead.

    Args:
        url (str): The SEC EDGAR url, e.g. SEC_COMPANY_TICKERS_URL.
        cache_file_name (str): The cache file's name in SEC_CACHE_DIR, e.g. "sec_company_tickers.json".

    Returns:
        The parsed JSON, or None if the download failed and there is no cached file. E.g. for
        SEC_COMPANY_TICKERS_URL: {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}
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


def lookup_sec_fund_registrant_name(cik: str):
    """
    Returns the registrant name in the SEC EDGAR submissions of a fund's 10-digit CIK, or None if there is none,
    e.g. "VANGUARD INDEX FUNDS" for "0000036405", VOO's CIK.

    The registrant is often a trust of several funds, e.g. VOO's is "VANGUARD INDEX FUNDS", which is why the ticker
    names file is used first.
    """
    submissions = load_sec_json(SEC_SUBMISSIONS_URL.format(cik=cik), f"sec_submissions_CIK{cik}.json")
    return (submissions or {}).get("name") or None


def lookup_sec_names(tickers: list) -> dict:
    """
    Looks up the name of each ticker in SEC EDGAR, e.g. ["NVDA", "QQQ", "XYZQ"] returns
    {"NVDA": "NVIDIA CORP", "QQQ": "INVESCO QQQ TRUST, SERIES 1"}.

    Company tickers are named by their title in company_tickers.json. ETF and mutual fund tickers are only in
    company_tickers_mf.json, which has no names, so they're named by their registrant
    (lookup_sec_fund_registrant_name).

    Tickers that aren't in SEC EDGAR are left out of the returned dictionary.
    """
    company_tickers = load_sec_json(SEC_COMPANY_TICKERS_URL, "sec_company_tickers.json") or {}
    company_names_by_ticker = {item["ticker"].upper(): item["title"] for item in company_tickers.values()}

    fund_tickers = load_sec_json(SEC_FUND_TICKERS_URL, "sec_company_tickers_mf.json") or {}
    # Each entry is [CIK, Series ID, Class ID, Ticker]
    fund_ciks_by_ticker = {entry[3].upper(): str(entry[0]).zfill(10) for entry in fund_tickers.get("data", [])}

    names_by_ticker = {}
    for ticker in tickers:
        # SEC tickers separate the share class with '-', e.g. BRK-B for BRK.B
        sec_ticker = ticker.upper().replace('.', '-')
        if sec_ticker in company_names_by_ticker:
            names_by_ticker[ticker] = company_names_by_ticker[sec_ticker]
        elif sec_ticker in fund_ciks_by_ticker:
            registrant_name = lookup_sec_fund_registrant_name(fund_ciks_by_ticker[sec_ticker])
            if registrant_name:
                names_by_ticker[ticker] = registrant_name
    return names_by_ticker


def lookup_ticker_names(tickers: list, ticker_names_file: str) -> dict:
    """
    Looks up the name of each ticker: from ticker_names_file if the ticker is in it, otherwise from SEC EDGAR.
    Tickers in ticker_names_file, and Taiwan tickers (TW_TICKER_PREFIX), which SEC EDGAR doesn't list, aren't looked
    up in SEC EDGAR.

    Args:
        tickers (list): Ticker symbols, e.g. ["EWT", "NVDA", "XYZQ"].
        ticker_names_file (str): The ticker names file, e.g. DEFAULT_TICKER_NAMES_FILE.

    Returns:
        dict: The name of each ticker that has one, e.g. {"EWT": "iShares MSCI Taiwan ETF (Taiwanese stocks)",
        "NVDA": "NVIDIA CORP"}: EWT from the ticker names file, NVDA from SEC EDGAR. Prints a warning listing the
        tickers without a name, like XYZQ.
    """
    file_names_by_ticker = load_ticker_names_file(ticker_names_file)
    names_by_ticker = {ticker: file_names_by_ticker[ticker.upper()] for ticker in tickers
                       if ticker.upper() in file_names_by_ticker}

    tickers_not_in_file = [ticker for ticker in tickers
                           if ticker not in names_by_ticker and not ticker.startswith(TW_TICKER_PREFIX)]
    sec_names_by_ticker = lookup_sec_names(tickers_not_in_file) if tickers_not_in_file else {}
    print(f"Ticker names: {len(names_by_ticker)} from {ticker_names_file}, {len(sec_names_by_ticker)} from SEC EDGAR")
    names_by_ticker.update(sec_names_by_ticker)

    unnamed_tickers = [ticker for ticker in tickers if ticker not in names_by_ticker]
    if unnamed_tickers:
        print(f"WARNING: No name found for {len(unnamed_tickers)} tickers: {', '.join(unnamed_tickers)}",
              file=sys.stderr)
    return names_by_ticker


def add_ticker_names(values_by_ticker: dict, ticker_names_file: str) -> dict:
    """
    Returns a copy of values_by_ticker with each ticker's name (lookup_ticker_names) as its first attribute, e.g.
    {"NVDA": {"Name": "NVIDIA CORP", "Current Value": 436959.0, "Previous Value": 438549.82, ...}, ...}

    The SUM_KEY and CASH_KEY entries, and tickers without a name, are copied unchanged. values_by_ticker is the
    output of calculate_values_and_weights.
    """
    tickers = [ticker for ticker in values_by_ticker if ticker not in (SUM_KEY, CASH_KEY)]
    names_by_ticker = lookup_ticker_names(tickers, ticker_names_file)
    return {ticker: {'Name': names_by_ticker[ticker], **attributes} if ticker in names_by_ticker else attributes
            for ticker, attributes in values_by_ticker.items()}


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

def write_prompt(template_path: str, portfolio_data: dict, output_path: str) -> None:
    """
    Writes the prompt template to output_path with PORTFOLIO_DATA_PLACEHOLDER replaced by portfolio_data as JSON
    indented by 2 spaces. E.g. the template line {{PORTFOLIO_HOLDING_DATA_JSON}} becomes:
    {
      "VOO": {
        "Name": "Vanguard S&P 500 ETF (S&P 500)",
        "Current Value": 1351.8,
        ...
      },
      ...
    }
    """
    with open(template_path, 'r') as f:
        template = f.read()
    prompt = template.replace(PORTFOLIO_DATA_PLACEHOLDER, json.dumps(portfolio_data, indent=2))
    with open(output_path, 'w') as f:
        f.write(prompt)
    print(f"\nLLM prompt written to: {output_path}")


def parse_args() -> argparse.Namespace:
    """
    Parses the command line, e.g.
        --portfolio_file portfolios/vicky.json --llm_prompt_template prompt_templates/daily_report_prompt_template.txt
    returns Namespace(portfolio_file='portfolios/vicky.json',
                      llm_prompt_template='prompt_templates/daily_report_prompt_template.txt',
                      output_prompt='prompt.txt', ticker_names_file=DEFAULT_TICKER_NAMES_FILE).
    """
    parser = argparse.ArgumentParser(description='Builds an LLM prompt from a portfolio and its real-time quotes.')
    parser.add_argument('--portfolio_file', type=str, required=True, help=
    'The path to the portfolio JSON file. The file should be in the format: {"TICKER": {"shares": <number>}}, '
    f'optionally with the cash amount as "{CASH_KEY}": {{"shares": <number>}}')
    parser.add_argument('--llm_prompt_template', type=str, required=True, help=
    f'The path to the LLM prompt template text file that contains {PORTFOLIO_DATA_PLACEHOLDER}.')
    parser.add_argument('--output_prompt', type=str, default=DEFAULT_OUTPUT_PROMPT_FILE, help=
    f'The output file name for the generated LLM prompt. Defaults to "{DEFAULT_OUTPUT_PROMPT_FILE}" '
    f'next to the prompt template.')
    parser.add_argument('--ticker_names_file', type=str, default=DEFAULT_TICKER_NAMES_FILE, help=
    'The path to a JSON file of ticker names, {"TICKER": "Name", ...}, used instead of the SEC EDGAR names, '
    f'which are often only the trust that issues an ETF. Defaults to {DEFAULT_TICKER_NAMES_FILE}.')
    return parser.parse_args()


def output_prompt_path(output_prompt: str, llm_prompt_template: str) -> str:
    """
    Returns the path to write the prompt to: the default file name goes next to the prompt template, e.g.
    ("prompt.txt", "prompt_templates/daily_report_prompt_template.txt") returns "prompt_templates/prompt.txt";
    any other output_prompt is returned unchanged.
    """
    if output_prompt == DEFAULT_OUTPUT_PROMPT_FILE:
        return os.path.join(os.path.dirname(llm_prompt_template), output_prompt)
    return output_prompt


def main():
    """
    Builds the prompt: loads the portfolio, fetches its quotes and converts them to USD, calculates values and
    weights, adds ticker names and writes the prompt. See the module docstring for the arguments, environment variables and exit status.
    """
    args = parse_args()

    shares_by_ticker, cash_amount = load_portfolio(args.portfolio_file)
    quotes = quotes_in_usd(fetch_stock_quotes(list(shares_by_ticker.keys())))

    quotes_with_shares = merge_shares_into_quotes(shares_by_ticker, quotes)
    values_by_ticker = calculate_values_and_weights(quotes_with_shares, cash_amount)
    portfolio_data = add_ticker_names(values_by_ticker, args.ticker_names_file)
    print(f"\n--- Portfolio value change from last trading day (top {NUM_TICKERS_TO_PRINT} tickers) ---")
    print(condensed_json(portfolio_data, NUM_TICKERS_TO_PRINT))

    write_prompt(args.llm_prompt_template, portfolio_data,
                 output_prompt_path(args.output_prompt, args.llm_prompt_template))


if __name__ == "__main__":
    main()
