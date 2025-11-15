import datetime
import json
import os
from http import HTTPStatus
import requests

from gcp_data_access import get_gcp_secret


# Placeholder for log function
def log(text: str, severity: str):
    """
    Logs a message.

    Args:
        text: The message to log.
        severity: The severity of the message (e.g., "ERROR", "WARNING").
    """
    print(f"[{severity}] {text}")


LOG_SEVERITY_ERROR = "ERROR"
LOG_SEVERITY_WARNING = "WARNING"
LOG_SEVERITY_DEBUG = "DEBUG"

access_token = None
trade_station_access_token_keep_alive = datetime.timedelta(minutes=19)
trade_station_token_url = "https://signin.tradestation.com/oauth/token"
trade_station_url = 'https://api.tradestation.com/v3'
trade_station_market_data = '/marketdata/stream/quotes/{symbols}'


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
        A dictionary containing the new access token and last modified time for each account,
        in the format:
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
    payload = get_gcp_secret(secret_name)
    TradeStation_OAuth0 = payload.data.decode("UTF-8")
    if not TradeStation_OAuth0:
        raise ValueError(
            f"TradeStation OAuth secret not found. Ensure {secret_name} exists in Secret Manager.")

    TradeStation_OAuth0_dict = json.loads(TradeStation_OAuth0)
    access_token_dict = {}

    for key, client_id_secret_refresh_token_dict in TradeStation_OAuth0_dict.items():
        client_id = client_id_secret_refresh_token_dict['client_id']
        client_secret = client_id_secret_refresh_token_dict['client_secret']
        refresh_token = client_id_secret_refresh_token_dict['refresh_token']

        payload = 'grant_type=refresh_token&client_id={}&client_secret={}&refresh_token={}'.format(
            client_id, client_secret, refresh_token
        )
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }

        try:
            token_response = requests.request("POST", trade_station_token_url, headers=headers, data=payload)
            token_response.raise_for_status()  # Raise an exception for HTTP errors

            local_access_token = token_response.json()['access_token']
            last_modified = datetime.datetime.now()
            local_access_token_dict = {
                'token': local_access_token,
                'last_modified': last_modified
            }
            access_token_dict[key] = local_access_token_dict
        except requests.exceptions.RequestException as e:
            log(text=f"Failed to refresh token for account {key}: {e}", severity=LOG_SEVERITY_ERROR)
            # Depending on requirements, you might want to re-raise or continue
            raise

    return access_token_dict


def refresh_global_access_token():
    """
    Refreshes the global access token if it's expired or about to expire.

    The token is refreshed if the last refresh was more than 19 minutes ago.
    The 20-minute expiration is based on TradeStation's documentation:
    https://api.tradestation.com/docs/fundamentals/authentication/refresh-tokens/

    Returns:
        The refreshed access token dictionary.
    """
    global access_token

    if access_token is None:
        access_token = refresh_access_token()
    else:
        # if one account's access token is too old, refresh all account's access token for simplicity.
        do_refresh_access_token = False
        for key, value in access_token.items():
            # Check if 'last_modified' exists and if access is too old
            if 'last_modified' not in value or \
                    datetime.datetime.now() - value['last_modified'] > trade_station_access_token_keep_alive:
                do_refresh_access_token = True
                break
        if do_refresh_access_token:
            access_token = refresh_access_token()

    return access_token


def get_tradestation_realtime_quotes(tickers: list[str] = ["VOO", "QQQ"]):
    """
    Fetches real-time quotes for a list of tickers from TradeStation.

    Args:
        tickers: A list of ticker symbols (e.g., ["VOO", "QQQ"]).

    Returns:
        A dictionary where keys are ticker symbols and values are the corresponding
        quote data from TradeStation.
    """
    # attempt to call Trade Station API to get real time price quote
    access_token = refresh_global_access_token()
    symbol_quotes = {}

    for key, value in access_token.items():
        if 'token' in value:
            trade_station_quote = '{}{}'.format(trade_station_url, trade_station_market_data.format(symbols=','.join(tickers)))
            headers = {
                'Authorization': 'Bearer {}'.format(value['token'])
            }
            with requests.get(trade_station_quote, headers=headers, stream=True, timeout=10) as quote_response:
                if quote_response.status_code == HTTPStatus.OK:
                    # 3. Iterate over the response line by line as data arrives.
                    for line in quote_response.iter_lines():
                        # Filter out keep-alive new lines
                        if line:
                            # The line is in bytes, so it needs to be decoded to a string
                            quote_json = json.loads(line.decode('utf-8'))
                            symbol_quotes[quote_json['Symbol']] = quote_json
                            if len(symbol_quotes) == len(tickers):
                                break

                else:
                    # This will raise an error for bad status codes (4xx or 5xx)
                    quote_response.raise_for_status()
            # Quotes have been fetched successfully, no need to try with other accounts.
            break
        else:
            error_text = 'Failed to get TradeStation access token from refresh token in secret {}'.format(
                os.environ.get('SECRET_NAME_TradeStation_OAuth0'))
            raise ValueError(error_text)

    return symbol_quotes


if __name__ == "__main__":
    print(get_tradestation_realtime_quotes())
