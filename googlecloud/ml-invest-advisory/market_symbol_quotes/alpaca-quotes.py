"""
Alpaca real-time US stock quotes for the get_us_ticker_quotes Cloud Function (see main.py and README.md).

The US quotes provider that replaced the retired TradeStation API (tradestation_obsolete.py). The quotes use the same field names as
TradeStation's quote snapshots ("Last", "PreviousClose", "NetChangePct", ...), so the portfolio report scripts in
portfolio_reports can consume either function.

Flow:
  1. get_alpaca_client() reads the API key and secret from the Secret Manager secret $ALPACA_SECRET_NAME and caches a
     StockHistoricalDataClient in the module-level `alpaca_client`, so requests served by the same Cloud Run instance
     reuse it. Alpaca API keys don't expire, so there is no token refresh.
  2. get_alpaca_realtime_quotes() requests snapshots for all tickers in one call to
     GET https://data.alpaca.markets/v2/stocks/snapshots via alpaca-py:
     https://alpaca.markets/sdks/python/market_data.html
  3. Each snapshot is converted to a TradeStation-style quote by snapshot_to_quote().

Data feed:
  Without $ALPACA_DATA_FEED, Alpaca picks the feed: SIP (all US exchanges) with an Algo Trader Plus subscription,
  otherwise IEX. IEX is a single exchange, so "Last" can lag the consolidated price for thinly traded symbols.
  Set ALPACA_DATA_FEED to one of alpaca.data.enums.DataFeed's values (e.g. sip, iex, delayed_sip) to pick one.

Errors:
  - alpaca.common.exceptions.APIError: Alpaca returned a non-200 response; alpaca-py already retries 429 and 504.
  - Symbols Alpaca returns no snapshot for (unknown symbols) or no last trade / previous close for are left out of the
    quotes and returned as per-symbol errors, e.g. [{"Symbol": "XYZ", "Error": "..."}].
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
    Converts an Alpaca snapshot to a quote with TradeStation's field names, e.g. for MSFT:
    {
      "Symbol": "MSFT", "Last": 509.355, "PreviousClose": 516.17, "NetChange": -6.815, "NetChangePct": -1.32,
      "Open": 515.0, "High": 517.2, "Low": 508.1, "Close": 509.355, "Volume": 12345678.0, "PreviousVolume": 23456789.0,
      "VWAP": 511.2, "Bid": 509.3, "BidSize": 100.0, "Ask": 509.4, "AskSize": 200.0,
      "TradeTime": "2026-10-16T19:20:42Z", "LastSize": 100.0, "LastVenue": "V"
    }
    NetChangePct is in percent, like TradeStation's. Prices are floats rather than TradeStation's strings.

    PreviousClose is the close of the trading day before the latest trade. Before the first regular-hours bar of a
    trading day, e.g. in pre-market, Alpaca's daily_bar is still the previous trading day's, so it is used as the
    previous close and the current day's Open/High/Low/Close/Volume/VWAP are left out.

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
        'Symbol': snapshot.symbol,
        'Last': trade.price,
        'PreviousClose': previous_bar.close,
        'NetChange': net_change,
        'NetChangePct': net_change / previous_bar.close * 100 if previous_bar.close else 0.0,
        'PreviousVolume': previous_bar.volume,
        'TradeTime': trade.timestamp.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'LastSize': trade.size,
        'LastVenue': getattr(trade.exchange, 'value', trade.exchange),
    }
    if session_bar is not None:
        quote.update({
            'Open': session_bar.open,
            'High': session_bar.high,
            'Low': session_bar.low,
            'Close': session_bar.close,
            'Volume': session_bar.volume,
            'VWAP': session_bar.vwap,
        })
    if snapshot.latest_quote is not None:
        quote.update({
            'Bid': snapshot.latest_quote.bid_price,
            'BidSize': snapshot.latest_quote.bid_size,
            'Ask': snapshot.latest_quote.ask_price,
            'AskSize': snapshot.latest_quote.ask_size,
        })
    return quote


def get_alpaca_realtime_quotes(tickers: list[str] = ["VOO", "QQQ"]):
    """
    Fetches real-time quotes for a list of tickers from Alpaca's stock snapshots.

    Args:
        tickers: A list of ticker symbols (e.g., ["VOO", "QQQ"]).

    Returns:
        A tuple of (symbol_quotes, symbol_errors), like tradestation_obsolete.get_tradestation_realtime_quotes().
        symbol_quotes is a dictionary where keys are ticker symbols and values are quotes in the format of
        snapshot_to_quote(). symbol_errors lists the symbols that could not be quoted,
        e.g. [{"Symbol": "XYZ", "Error": "..."}].

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
            symbol_errors.append({'Symbol': symbol, 'Error': 'Alpaca returned no snapshot for the symbol'})
            continue
        try:
            symbol_quotes[symbol] = snapshot_to_quote(snapshots[symbol])
        except ValueError as e:
            symbol_errors.append({'Symbol': symbol, 'Error': str(e)})
    if symbol_errors:
        log(text=f"Alpaca quote errors: {json.dumps(symbol_errors)}", severity=LOG_SEVERITY_WARNING)

    return symbol_quotes, symbol_errors


if __name__ == "__main__":
    print(get_alpaca_realtime_quotes())
