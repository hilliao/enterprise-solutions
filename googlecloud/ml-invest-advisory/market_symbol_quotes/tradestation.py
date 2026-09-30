"""
TradeStation real-time US stock quotes for the get_us_stock_quotes Cloud Function (see main.py and README.md).

Flow:
  1. refresh_access_token() reads client_id / client_secret / refresh_token per account from the Secret Manager
     secret $TRADE_STATION_OAUTH_SECRET_NAME (default TradeStation_OAuth0) and exchanges each refresh token for an
     access token at https://signin.tradestation.com/oauth/token.
  2. refresh_global_access_token() caches the access tokens in the module-level `access_token`, so all requests
     served by the same Cloud Run instance reuse them until they approach expiry.
  3. get_tradestation_realtime_quotes() calls GET https://api.tradestation.com/v3/marketdata/quotes/{symbols} with the
     first account's access token and returns (quotes keyed by symbol, per-symbol errors).

Access token lifecycle:
  TradeStation access tokens are valid for 20 minutes (expires_in=1200 in the token response). A new one should only
  be requested when the current one is approaching or past expiry, not on every request:
  https://api.tradestation.com/docs/fundamentals/authentication/refresh-tokens/
  - Proactive refresh: each token's expiry is computed from the response's expires_in, counted from when the token
    request was sent, and all tokens are refreshed ACCESS_TOKEN_EXPIRY_MARGIN before the earliest expiry.
  - Reactive refresh: if the quotes request returns 401 or 403, the token may have expired or been revoked early, so
    the tokens are refreshed and the request is retried once. A token younger than
    ACCESS_TOKEN_MIN_AGE_FOR_FORCED_REFRESH is kept, because then the token is unlikely to be the cause (e.g.
    TradeStation rejecting Cloud Run's egress IP) and refreshing on every failing request would only add load.
  - Refreshes are serialized with access_token_lock, so concurrent requests in one instance refresh once.
  - Times are timezone-aware UTC, so a local DST change can't make a token look younger than it is.
  - If TradeStation returns a new refresh token (rotating refresh tokens), a warning is logged: the secret is not
    updated, and rotating refresh tokens have a 24-hour absolute lifetime.

Errors:
  - TradeStationApiError: the quotes request returned a non-200 response, after the retry above. The ERROR log
    includes the age of the access token used, to tell an expired token apart from other causes of 403.
  - requests.exceptions.RequestException: the token request failed; logged with TradeStation's response and re-raised.
"""
import datetime
import json
import os
import threading
from http import HTTPStatus
import requests

from gcp_data_access import get_gcp_secret


def log(text: str, severity: str):
    """
    Logs a message as structured JSON so Cloud Logging records the severity:
    https://cloud.google.com/run/docs/logging#using-json

    Args:
        text: The message to log.
        severity: The severity of the message (e.g., "ERROR", "WARNING").
    """
    print(json.dumps({'severity': severity, 'message': text}), flush=True)


LOG_SEVERITY_ERROR = "ERROR"
LOG_SEVERITY_WARNING = "WARNING"
LOG_SEVERITY_DEBUG = "DEBUG"

# Cached access tokens per account, see refresh_access_token() for the format. Guarded by access_token_lock.
access_token = None
access_token_lock = threading.Lock()
# Refresh access tokens this long before they expire, so a token doesn't expire between the check and the request.
ACCESS_TOKEN_EXPIRY_MARGIN = datetime.timedelta(minutes=2)
# Used when the token response has no expires_in; TradeStation documents a 20-minute lifetime.
DEFAULT_ACCESS_TOKEN_LIFETIME = datetime.timedelta(minutes=20)
# After a 401/403 from the quotes API, only replace access tokens older than this. Limits token refreshes to one per
# 5 minutes per instance while TradeStation keeps rejecting requests for reasons other than the token.
ACCESS_TOKEN_MIN_AGE_FOR_FORCED_REFRESH = datetime.timedelta(minutes=5)
trade_station_token_url = "https://signin.tradestation.com/oauth/token"
trade_station_url = 'https://api.tradestation.com/v3'
trade_station_market_data = '/marketdata/quotes/{symbols}'
# Sample response of GET {trade_station_url}{trade_station_market_data} with symbols=GOOG,SOXX:
# {
#   "Quotes": [
#     {
#       "Symbol": "GOOG",
#       "Open": "340.64999",
#       "High": "349.05499",
#       "Low": "337.72",
#       "PreviousClose": "337.32001",
#       "Last": "346.2",
#       "Ask": "346.36",
#       "AskSize": "40",
#       "Bid": "346",
#       "BidSize": "80",
#       "NetChange": "8.87999",
#       "NetChangePct": "2.63251207658864",
#       "High52Week": "404.47",
#       "High52WeekTimestamp": "2026-05-18T00:00:00Z",
#       "Low52Week": "236.685",
#       "Low52WeekTimestamp": "2025-10-10T00:00:00Z",
#       "Volume": "23212592",
#       "PreviousVolume": "14002319",
#       "Close": "340.73999",
#       "DailyOpenInterest": "0",
#       "Restrictions": [],
#       "TradeTime": "2026-09-30T20:21:49Z",
#       "TickSizeTier": "0",
#       "MarketFlags": {
#         "IsDelayed": false,
#         "IsHardToBorrow": false,
#         "IsBats": false,
#         "IsHalted": false
#       },
#       "LastSize": "125",
#       "LastVenue": "ARCX",
#       "VWAP": "343.449924334431"
#     },
#     {
#       "Symbol": "SOXX",
#       "Open": "568.72498",
#       "High": "572.32001",
#       "Low": "564.01001",
#       "PreviousClose": "567.44",
#       "Last": "570.01",
#       "Ask": "570.57",
#       "AskSize": "280",
#       "Bid": "569.59",
#       "BidSize": "40",
#       "NetChange": "2.57",
#       "NetChangePct": "0.452911321020725",
#       "High52Week": "655.95001",
#       "High52WeekTimestamp": "2026-06-22T00:00:00Z",
#       "Low52Week": "260.44",
#       "Low52WeekTimestamp": "2025-11-21T00:00:00Z",
#       "Volume": "4345823",
#       "PreviousVolume": "5131460",
#       "Close": "568.64001",
#       "DailyOpenInterest": "0",
#       "Restrictions": [],
#       "TradeTime": "2026-09-30T20:21:45Z",
#       "TickSizeTier": "0",
#       "MarketFlags": {
#         "IsDelayed": false,
#         "IsHardToBorrow": false,
#         "IsBats": false,
#         "IsHalted": false
#       },
#       "LastSize": "40",
#       "LastVenue": "ARCX",
#       "VWAP": "567.865505646382"
#     }
#   ]
# }


class TradeStationApiError(Exception):
    """Raised when the TradeStation API returns a non-200 response; keeps the response body as detail."""

    def __init__(self, status_code: int, url: str, detail):
        super().__init__(f"TradeStation API returned {status_code} for url: {url}")
        self.status_code = status_code
        self.detail = detail


def refresh_access_token(secret_name: str = os.environ.get('TRADE_STATION_OAUTH_SECRET_NAME', 'TradeStation_OAuth0')):
    """Refreshes the TradeStation access token using the refresh token.

    The secret should be in the format:
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

    Args:
        secret_name: The name of the secret in Secret Manager.

    Returns:
        A dictionary containing the new access token, the time it was requested and the time it expires
        (both timezone-aware UTC) for each account, in the format:
        {
          "account_number_0":
          {
            "token": "aaa",
            "last_modified": datetime.datetime,
            "expires_at": datetime.datetime
          },
          "account_number_1":
          {
            "token": "hhh",
            "last_modified": datetime.datetime,
            "expires_at": datetime.datetime
          }
        }

    Raises:
        requests.exceptions.RequestException: If the token request for any account fails.
    """
    payload = get_gcp_secret(secret_name)
    TradeStation_OAuth0 = payload.data.decode("UTF-8")
    if not TradeStation_OAuth0:
        raise ValueError(
            f"TradeStation OAuth secret not found. Ensure {secret_name} exists in Secret Manager.")

    TradeStation_OAuth0_dict = json.loads(TradeStation_OAuth0)
    access_token_dict = {}

    for key, client_id_secret_refresh_token_dict in TradeStation_OAuth0_dict.items():
        refresh_token = client_id_secret_refresh_token_dict['refresh_token']
        # requests URL-encodes a dict payload and sends it as application/x-www-form-urlencoded,
        # so secrets containing characters like '&' or '+' are sent intact.
        payload = {
            'grant_type': 'refresh_token',
            'client_id': client_id_secret_refresh_token_dict['client_id'],
            'client_secret': client_id_secret_refresh_token_dict['client_secret'],
            'refresh_token': refresh_token,
        }

        try:
            # Count the token lifetime from before the request is sent, so the computed expiry is never later
            # than TradeStation's.
            requested_at = datetime.datetime.now(datetime.timezone.utc)
            token_response = requests.post(trade_station_token_url, data=payload, timeout=10)
            token_response.raise_for_status()  # Raise an exception for HTTP errors

            token_response_json = token_response.json()
            expires_in = token_response_json.get('expires_in')
            lifetime = datetime.timedelta(seconds=int(expires_in)) if expires_in else DEFAULT_ACCESS_TOKEN_LIFETIME
            access_token_dict[key] = {
                'token': token_response_json['access_token'],
                'last_modified': requested_at,
                'expires_at': requested_at + lifetime
            }
            if token_response_json.get('refresh_token', refresh_token) != refresh_token:
                log(text=f"TradeStation returned a new refresh token for account {key}, so rotating refresh tokens "
                         f"are enabled. {secret_name} is not updated and its refresh token has a 24-hour absolute "
                         f"lifetime.", severity=LOG_SEVERITY_WARNING)
        except requests.exceptions.RequestException as e:
            response_text = e.response.text if e.response is not None else ''
            log(text=f"Failed to refresh token for account {key}: {e}, response: {response_text}",
                severity=LOG_SEVERITY_ERROR)
            # Depending on requirements, you might want to re-raise or continue
            raise

    return access_token_dict


def is_access_token_expiring(account_access_token: dict, now: datetime.datetime) -> bool:
    """
    Returns True if an account's cached access token is missing, expired, or expires within ACCESS_TOKEN_EXPIRY_MARGIN.

    Args:
        account_access_token: One account's entry from refresh_access_token().
        now: The current timezone-aware UTC time.
    """
    return 'token' not in account_access_token or 'expires_at' not in account_access_token or \
        now >= account_access_token['expires_at'] - ACCESS_TOKEN_EXPIRY_MARGIN


def refresh_global_access_token(force_refresh: bool = False):
    """
    Returns the cached access tokens, refreshing them first if needed.

    The tokens are refreshed when:
    - there are no cached tokens yet (first request served by this instance), or
    - any account's token expires within ACCESS_TOKEN_EXPIRY_MARGIN, based on the token response's expires_in.
      TradeStation access tokens are valid for 20 minutes and should only be renewed when approaching expiry:
      https://api.tradestation.com/docs/fundamentals/authentication/refresh-tokens/
    - force_refresh is True and the tokens are at least ACCESS_TOKEN_MIN_AGE_FOR_FORCED_REFRESH old. The caller sets
      force_refresh after TradeStation rejects a token that hasn't expired yet by our clock, e.g. when it was
      revoked. Younger tokens are kept: another request may have just refreshed them, or the rejection has a
      cause other than the token, and a refresh on every failing request would hammer the token endpoint.

    The check-and-refresh runs under access_token_lock, so concurrent requests don't each refresh.

    Args:
        force_refresh: True if TradeStation just rejected the cached token with 401 or 403.

    Returns:
        The access token dictionary, in the format returned by refresh_access_token().
    """
    global access_token

    with access_token_lock:
        now = datetime.datetime.now(datetime.timezone.utc)
        if access_token is None:
            access_token = refresh_access_token()
        elif any(is_access_token_expiring(value, now) for value in access_token.values()):
            # if one account's access token is expiring, refresh all account's access token for simplicity.
            access_token = refresh_access_token()
        elif force_refresh:
            token_age = now - max(value['last_modified'] for value in access_token.values())
            if token_age >= ACCESS_TOKEN_MIN_AGE_FOR_FORCED_REFRESH:
                log(text=f"Refreshing TradeStation access tokens issued {int(token_age.total_seconds())}s ago "
                         f"after TradeStation rejected them before expiry", severity=LOG_SEVERITY_WARNING)
                access_token = refresh_access_token()

        return access_token


def get_quote_response(url: str, token: str) -> requests.Response:
    """Sends a GET request for quote snapshots to url with token as the bearer access token."""
    return requests.get(url, headers={'Authorization': 'Bearer {}'.format(token)}, timeout=10)


def get_tradestation_realtime_quotes(tickers: list[str] = ["VOO", "QQQ"]):
    """
    Fetches real-time quotes for a list of tickers from TradeStation.

    Args:
        tickers: A list of ticker symbols (e.g., ["VOO", "QQQ"]).

    Returns:
        A tuple of (symbol_quotes, symbol_errors). symbol_quotes is a dictionary where keys are ticker
        symbols and values are the corresponding quote data from TradeStation. symbol_errors is the
        TradeStation "Errors" list for symbols that could not be quoted, e.g. [{"Symbol": "XYZ", "Error": "..."}].

    If TradeStation returns 401 or 403, the access token is refreshed (see refresh_global_access_token) and the
    request is retried once with the new token.

    Raises:
        TradeStationApiError: If TradeStation returns a non-200 response, after the retry.
    """
    # attempt to call Trade Station API to get real time price quote
    access_token = refresh_global_access_token()
    symbol_quotes = {}
    symbol_errors = []

    for key, value in access_token.items():
        if 'token' in value:
            trade_station_quote = '{}{}'.format(trade_station_url, trade_station_market_data.format(symbols=','.join(tickers)))
            account_access_token = value
            quote_response = get_quote_response(trade_station_quote, account_access_token['token'])
            if quote_response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                # The token may have expired or been revoked earlier than expires_in says. If the token was
                # replaced, retry once; if it was kept because it's recent, retrying would repeat the same error.
                refreshed_access_token = refresh_global_access_token(force_refresh=True).get(key, {})
                if refreshed_access_token.get('token', account_access_token['token']) != account_access_token['token']:
                    log(text=f"TradeStation API returned {quote_response.status_code} for url: {trade_station_quote}, "
                             f"retrying with a refreshed access token", severity=LOG_SEVERITY_WARNING)
                    account_access_token = refreshed_access_token
                    quote_response = get_quote_response(trade_station_quote, account_access_token['token'])
            if quote_response.status_code == HTTPStatus.OK:
                quote_response_json = quote_response.json()
                symbol_errors = quote_response_json.get('Errors', [])
                if symbol_errors:
                    log(text=f"TradeStation quote errors: {json.dumps(symbol_errors)}", severity=LOG_SEVERITY_WARNING)
                for quote_json in quote_response_json.get('Quotes', []):
                    symbol_quotes[quote_json['Symbol']] = quote_json
            else:
                try:
                    detail = quote_response.json()
                except ValueError:
                    detail = quote_response.text
                # A token that is minutes old when rejected points to a cause other than token expiry.
                token_age = datetime.datetime.now(datetime.timezone.utc) - account_access_token['last_modified']
                log(text=f"TradeStation API returned {quote_response.status_code} for url: {trade_station_quote}, "
                         f"access token issued {int(token_age.total_seconds())}s ago, "
                         f"response: {quote_response.text}", severity=LOG_SEVERITY_ERROR)
                raise TradeStationApiError(quote_response.status_code, trade_station_quote, detail)
            # Quotes have been fetched successfully, no need to try with other accounts.
            break
        else:
            error_text = 'Failed to get TradeStation access token from refresh token in secret {}'.format(
                os.environ.get('TRADE_STATION_OAUTH_SECRET_NAME'))
            raise ValueError(error_text)

    return symbol_quotes, symbol_errors


if __name__ == "__main__":
    print(get_tradestation_realtime_quotes())
