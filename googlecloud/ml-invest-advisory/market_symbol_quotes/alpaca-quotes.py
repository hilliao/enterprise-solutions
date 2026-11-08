"""
Alpaca real-time US stock quotes for the get_us_ticker_quotes Cloud Function (see main.py and README.md).

The quotes are read by the portfolio report scripts in portfolio_reports (build_portfolio_prompt.py), which need
"price" and "previous-close"; see snapshot_to_quote() for all fields.

Flow:
  1. get_alpaca_client() reads the API key and secret from the Secret Manager secret $ALPACA_SECRET_NAME and caches a
     StockHistoricalDataClient in the module-level `alpaca_client`, so requests served by the same Cloud Run instance
     reuse it. Alpaca API keys don't expire, so there is no token refresh.
  2. get_alpaca_realtime_quotes() requests snapshots for all tickers in one call to
     GET https://data.alpaca.markets/v2/stocks/snapshots via alpaca-py:
     https://alpaca.markets/sdks/python/market_data.html
  3. Each snapshot is converted to a quote by snapshot_to_quote().

Data feed:
  Without $ALPACA_DATA_FEED, Alpaca picks the feed: SIP (all US exchanges) with an Algo Trader Plus subscription,
  otherwise IEX. IEX is a single exchange, so "price" can lag the consolidated price for thinly traded symbols.
  Set ALPACA_DATA_FEED to one of alpaca.data.enums.DataFeed's values (e.g. sip, iex, delayed_sip) to pick one.

Errors:
  - alpaca.common.exceptions.APIError: Alpaca returned a non-200 response; alpaca-py already retries 429 and 504.
  - Symbols Alpaca returns no snapshot for (unknown symbols) or no last trade / previous close for are left out of the
    quotes and returned as per-symbol errors, e.g. [{"symbol": "XYZ", "error": "..."}].
"""
import datetime
import json
import os
import threading
from zoneinfo import ZoneInfo

import yaml
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.models import Snapshot
from alpaca.data.requests import StockSnapshotRequest

from gcp_data_access import get_gcp_secret
from structured_logging import log, LOG_SEVERITY_WARNING

# Secret Manager secret in $PROJECT_ID with the Alpaca API key, set by deploy.sh, in the format:
# key: AKXXXXXXXXXXXXXXXXXX
# secret: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# 'or' also falls back to the default when the variable is set but empty.
ALPACA_SECRET_NAME = os.environ.get('ALPACA_SECRET_NAME') or 'alpaca-api-key'
# Daily bar timestamps are midnight in the exchange's time zone.
MARKET_TIME_ZONE = ZoneInfo('America/New_York')

# Cached data client, created on the first request. Guarded by alpaca_client_lock.
alpaca_client = None
alpaca_client_lock = threading.Lock()


def get_alpaca_client() -> StockHistoricalDataClient:
    """Returns the cached Alpaca market data client, creating it from the ALPACA_SECRET_NAME secret on first use."""
    global alpaca_client

    with alpaca_client_lock:
        if alpaca_client is None:
            alpaca_api_key = yaml.safe_load(get_gcp_secret(ALPACA_SECRET_NAME).data.decode("UTF-8")) or {}
            if not alpaca_api_key.get('key') or not alpaca_api_key.get('secret'):
                raise ValueError(f"Secret {ALPACA_SECRET_NAME} must be YAML with 'key' and 'secret' attributes.")
            alpaca_client = StockHistoricalDataClient(api_key=alpaca_api_key['key'],
                                                      secret_key=alpaca_api_key['secret'])
        return alpaca_client


def market_date(timestamp: datetime.datetime) -> datetime.date:
    """Returns the trading date of a timezone-aware timestamp in the exchange's time zone."""
    return timestamp.astimezone(MARKET_TIME_ZONE).date()


def snapshot_to_quote(snapshot: Snapshot) -> dict:
    """
    Converts an Alpaca snapshot to a quote, e.g. for VOO after the close on Friday 2026-11-06:
    {
      "symbol": "VOO", "price": 675.9, "previous-close": 673.94, "net-change": 1.96, "net-change-%": 0.29,
      "trade-time": "2026-11-06T21:00:03Z", "open": 675.435, "high": 681.44, "low": 675.34, "close": 676.02,
      "volume": 109275.0, "bid": 655.12, "ask": 696.49
    }
    price is the latest trade's price, including pre-market and after-hours trades; close is the regular session's.
    net-change is price - previous-close, rounded to 4 decimals; net-change-% is in percent, rounded to 2 decimals.
    trade-time is the latest trade's time in UTC.

    previous-close is the close of the trading day before the latest trade. Before the first regular-hours bar of a
    trading day, e.g. in pre-market, Alpaca's daily_bar is still the previous trading day's, so it is used as the
    previous close and the current day's open/high/low/close/volume are left out. bid and ask are left out when
    Alpaca has no latest quote.

    Raises:
        ValueError: If the snapshot has no latest trade or no previous close.
    """
    trade = snapshot.latest_trade
    if trade is None:
        raise ValueError('Alpaca snapshot has no latest trade')

    if snapshot.daily_bar is not None and market_date(snapshot.daily_bar.timestamp) < market_date(trade.timestamp):
        session_bar, previous_bar = None, snapshot.daily_bar
    else:
        session_bar, previous_bar = snapshot.daily_bar, snapshot.previous_daily_bar
    if previous_bar is None:
        raise ValueError('Alpaca snapshot has no previous daily bar for the previous close')

    net_change = trade.price - previous_bar.close
    quote = {
        'symbol': snapshot.symbol,
        'price': trade.price,
        'previous-close': previous_bar.close,
        'net-change': round(net_change, 4),
        'net-change-%': round(net_change / previous_bar.close * 100, 2) if previous_bar.close else 0.0,
        'trade-time': trade.timestamp.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    if session_bar is not None:
        quote.update({
            'open': session_bar.open,
            'high': session_bar.high,
            'low': session_bar.low,
            'close': session_bar.close,
            'volume': session_bar.volume,
        })
    if snapshot.latest_quote is not None:
        quote.update({
            'bid': snapshot.latest_quote.bid_price,
            'ask': snapshot.latest_quote.ask_price,
        })
    return quote


def get_alpaca_realtime_quotes(tickers: list[str] = ["VOO", "QQQ"]):
    """
    Fetches real-time quotes for a list of tickers from Alpaca's stock snapshots.

    Args:
        tickers: A list of ticker symbols (e.g., ["VOO", "QQQ"]).

    Returns:
        A tuple of (symbol_quotes, symbol_errors). symbol_quotes is a dictionary where keys are ticker symbols and
        values are quotes in the format of snapshot_to_quote(). symbol_errors lists the symbols that could not be
        quoted, e.g. [{"symbol": "XYZ", "error": "..."}].

    Raises:
        alpaca.common.exceptions.APIError: If Alpaca returns a non-200 response.
    """
    symbols = list(dict.fromkeys(ticker.upper() for ticker in tickers))
    feed = os.environ.get('ALPACA_DATA_FEED')
    snapshots = get_alpaca_client().get_stock_snapshot(
        StockSnapshotRequest(symbol_or_symbols=symbols, feed=DataFeed(feed) if feed else None))

    symbol_quotes = {}
    symbol_errors = []
    for symbol in symbols:
        if symbol not in snapshots:
            symbol_errors.append({'symbol': symbol, 'error': 'Alpaca returned no snapshot for the symbol'})
            continue
        try:
            symbol_quotes[symbol] = snapshot_to_quote(snapshots[symbol])
        except ValueError as e:
            symbol_errors.append({'symbol': symbol, 'error': str(e)})
    if symbol_errors:
        log(text=f"Alpaca quote errors: {json.dumps(symbol_errors)}", severity=LOG_SEVERITY_WARNING)

    return symbol_quotes, symbol_errors


if __name__ == "__main__":
    print(get_alpaca_realtime_quotes())
