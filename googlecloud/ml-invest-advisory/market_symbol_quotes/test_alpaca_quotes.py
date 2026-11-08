"""
Unit tests for alpaca-quotes.py, with Alpaca's snapshots and client mocked:

    python -m pytest -v test_alpaca_quotes.py
"""
import datetime
import importlib
from types import SimpleNamespace
from unittest import mock

import pytest

# alpaca-quotes.py has a hyphen in its name, so it can't be imported with an import statement.
alpaca_quotes = importlib.import_module('alpaca-quotes')

UTC = datetime.timezone.utc
# Daily bar timestamps are midnight in New York, 04:00 or 05:00 UTC.
FRIDAY_BAR_TIME = datetime.datetime(2026, 11, 6, 5, 0, tzinfo=UTC)
THURSDAY_BAR_TIME = datetime.datetime(2026, 11, 5, 5, 0, tzinfo=UTC)
FRIDAY_CLOSE_TIME = datetime.datetime(2026, 11, 6, 21, 0, 3, tzinfo=UTC)
MONDAY_PRE_MARKET_TIME = datetime.datetime(2026, 11, 9, 12, 30, tzinfo=UTC)


def bar(timestamp, close, open_=675.435, high=681.44, low=675.34, volume=109275.0):
    return SimpleNamespace(timestamp=timestamp, open=open_, high=high, low=low, close=close, volume=volume,
                           vwap=678.08)


def snapshot(trade_time=FRIDAY_CLOSE_TIME, price=675.9, daily_bar=None, previous_daily_bar=None,
             latest_quote=SimpleNamespace(bid_price=655.12, bid_size=40.0, ask_price=696.49, ask_size=40.0)):
    return SimpleNamespace(
        symbol='VOO',
        latest_trade=SimpleNamespace(price=price, timestamp=trade_time, size=120.0, exchange='V')
        if trade_time else None,
        daily_bar=daily_bar if daily_bar is not None else bar(FRIDAY_BAR_TIME, close=676.02),
        previous_daily_bar=previous_daily_bar if previous_daily_bar is not None else bar(THURSDAY_BAR_TIME, 673.94),
        latest_quote=latest_quote,
    )


def test_snapshot_to_quote_after_the_close():
    assert alpaca_quotes.snapshot_to_quote(snapshot()) == {
        'symbol': 'VOO', 'price': 675.9, 'previous-close': 673.94, 'net-change': 1.96, 'net-change-%': 0.29,
        'trade-time': '2026-11-06T21:00:03Z', 'open': 675.435, 'high': 681.44, 'low': 675.34, 'close': 676.02,
        'volume': 109275.0, 'bid': 655.12, 'ask': 696.49,
    }


def test_snapshot_to_quote_in_pre_market_uses_daily_bar_as_previous_close():
    # Before Monday's first regular-hours bar, daily_bar is still Friday's.
    quote = alpaca_quotes.snapshot_to_quote(snapshot(trade_time=MONDAY_PRE_MARKET_TIME, price=680.0))

    assert quote['previous-close'] == 676.02
    assert quote['net-change'] == 3.98
    assert quote['net-change-%'] == 0.59
    for session_field in ('open', 'high', 'low', 'close', 'volume'):
        assert session_field not in quote


def test_snapshot_to_quote_without_latest_quote_leaves_out_bid_and_ask():
    quote = alpaca_quotes.snapshot_to_quote(snapshot(latest_quote=None))

    assert 'bid' not in quote and 'ask' not in quote


def test_snapshot_to_quote_leaves_out_uncommon_fields():
    quote = alpaca_quotes.snapshot_to_quote(snapshot())

    assert set(quote) == {'symbol', 'price', 'previous-close', 'net-change', 'net-change-%', 'trade-time',
                          'open', 'high', 'low', 'close', 'volume', 'bid', 'ask'}


def test_snapshot_to_quote_without_latest_trade_raises_value_error():
    with pytest.raises(ValueError, match='no latest trade'):
        alpaca_quotes.snapshot_to_quote(snapshot(trade_time=None))


def test_snapshot_to_quote_without_previous_close_raises_value_error():
    no_previous_bar = snapshot()
    no_previous_bar.previous_daily_bar = None

    with pytest.raises(ValueError, match='no previous daily bar'):
        alpaca_quotes.snapshot_to_quote(no_previous_bar)


def test_realtime_quotes_upper_cases_symbols_and_reports_errors(monkeypatch):
    client = mock.Mock()
    client.get_stock_snapshot.return_value = {'VOO': snapshot()}
    monkeypatch.setattr(alpaca_quotes, 'get_alpaca_client', lambda: client)

    quotes, errors = alpaca_quotes.get_alpaca_realtime_quotes(['voo', 'VOO', 'xyzq'])

    assert list(quotes) == ['VOO']
    assert quotes['VOO']['price'] == 675.9
    assert errors == [{'symbol': 'XYZQ', 'error': 'Alpaca returned no snapshot for the symbol'}]
    assert client.get_stock_snapshot.call_args.args[0].symbol_or_symbols == ['VOO', 'XYZQ']
