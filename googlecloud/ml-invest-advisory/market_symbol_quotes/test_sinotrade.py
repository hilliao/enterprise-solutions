"""
Tests for sinotrade.get_sinotrade_snapshots().

The offline tests mock Shioaji and Secret Manager. The live test logs in to the SinoTrade simulation server
with the API key in the "sinotrade-api-key" secret; it runs only when PROJECT_ID and TW_NATIONAL_ID are set
and Application Default Credentials can read that secret:

    gcloud auth application-default login
    PROJECT_ID=... TW_NATIONAL_ID=... python -m pytest -v test_sinotrade.py
"""
import datetime
import json
import os
from types import SimpleNamespace
from unittest import mock

import pytest
import shioaji as sj

import sinotrade

LIVE_SYMBOLS = ['2330', '006208', '00662']


@pytest.fixture
def fake_api(monkeypatch):
    """Replaces sj.Shioaji with a mock whose contracts.get(symbol) returns a contract named after the symbol."""
    monkeypatch.setenv('TW_NATIONAL_ID', 'TESTID')
    monkeypatch.setattr(sinotrade, 'sinotrade_api_keys', None)
    monkeypatch.setattr(sinotrade, 'get_sinotrade_api_key',
                        mock.Mock(return_value={'TESTID': {'api_key': 'key', 'api_key_secret': 'secret'}}))
    api = mock.MagicMock()
    api.contracts.get.side_effect = lambda symbol: None if symbol == 'NOPE' else f'contract-{symbol}'
    api.snapshots.side_effect = lambda contracts: [f'snapshot-{c}' for c in contracts]
    shioaji_class = mock.Mock(return_value=api)
    monkeypatch.setattr(sinotrade.sj, 'Shioaji', shioaji_class)
    return shioaji_class, api


def test_snapshots_logs_in_to_simulation_and_requests_each_symbol(fake_api):
    shioaji_class, api = fake_api

    snapshots = sinotrade.get_sinotrade_snapshots(['2330', '0050'])

    shioaji_class.assert_called_once_with(simulation=True)
    api.login.assert_called_once_with(api_key='key', secret_key='secret')
    api.snapshots.assert_called_once_with(['contract-2330', 'contract-0050'])
    assert snapshots == ['snapshot-contract-2330', 'snapshot-contract-0050']
    api.logout.assert_called_once()


def test_snapshots_unknown_symbol_raises_key_error_and_logs_out(fake_api):
    shioaji_class, api = fake_api

    with pytest.raises(KeyError, match='NOPE'):
        sinotrade.get_sinotrade_snapshots(['2330', 'NOPE'])

    api.snapshots.assert_not_called()
    api.logout.assert_called_once()


def snapshot_2330(**fields):
    """A Snapshot of 2330 after the close on Friday 2026-11-06, as returned by the simulation server."""
    return SimpleNamespace(**{
        'ts': 1793975400000000000, 'code': '2330', 'exchange': 'TSE', 'open': 2020, 'high': 2195, 'low': 2020,
        'close': 2135, 'tick_type': sj.TickType.Sell, 'change_price': -105, 'change_rate': -4.68,
        'average_price': 2093.18, 'volume': 106, 'total_volume': 97065, 'buy_price': 2135, 'buy_volume': 12,
        'sell_price': 2140, 'sell_volume': 1039, **fields})


def test_snapshot_time_to_utc_reads_ts_as_taiwan_time():
    assert sinotrade.snapshot_time_to_utc(1793975400000000000) == datetime.datetime(
        2026, 11, 6, 6, 30, tzinfo=datetime.timezone.utc)


def test_snapshot_to_quote():
    assert sinotrade.snapshot_to_quote(snapshot_2330()) == {
        'symbol': '2330', 'price': 2135.0, 'previous-close': 2240.0, 'net-change': -105.0, 'net-change-%': -4.68,
        'trade-time': '2026-11-06T06:30:00Z', 'open': 2020.0, 'high': 2195.0, 'low': 2020.0, 'bid': 2135.0,
        'ask': 2140.0, 'currency': 'TWD',
    }


def test_snapshot_to_quote_rounds_previous_close():
    quote = sinotrade.snapshot_to_quote(snapshot_2330(close=113.35, change_price=-5.4, change_rate=-4.5432))

    assert (quote['previous-close'], quote['net-change'], quote['net-change-%']) == (118.75, -5.4, -4.54)


def test_quotes_skip_unknown_symbols_and_log_out(fake_api):
    shioaji_class, api = fake_api
    api.snapshots.side_effect = lambda contracts: [snapshot_2330(code=c.removeprefix('contract-')) for c in contracts]

    quotes, errors = sinotrade.get_sinotrade_quotes(['2330', 'nope', '2330'])

    assert list(quotes) == ['2330']
    assert quotes['2330']['price'] == 2135.0
    assert errors == [{'symbol': 'NOPE', 'error': 'SinoTrade has no contract for the symbol'}]
    api.snapshots.assert_called_once_with(['contract-2330'])
    api.logout.assert_called_once()


def test_quotes_with_only_unknown_symbols_requests_no_snapshots(fake_api):
    shioaji_class, api = fake_api

    assert sinotrade.get_sinotrade_quotes(['nope']) == (
        {}, [{'symbol': 'NOPE', 'error': 'SinoTrade has no contract for the symbol'}])
    api.snapshots.assert_not_called()


def test_snapshots_reads_api_key_secret_once(fake_api):
    sinotrade.get_sinotrade_snapshots(['2330'])
    sinotrade.get_sinotrade_snapshots(['2330'])

    sinotrade.get_sinotrade_api_key.assert_called_once()


def test_snapshots_unknown_national_id_raises_key_error(fake_api, monkeypatch):
    monkeypatch.setenv('TW_NATIONAL_ID', 'OTHERID')

    with pytest.raises(KeyError):
        sinotrade.get_sinotrade_snapshots(['2330'])


@pytest.fixture(scope='module')
def live_snapshots():
    missing = [name for name in ('PROJECT_ID', 'TW_NATIONAL_ID') if not os.environ.get(name)]
    if missing:
        pytest.skip(f"set {' and '.join(missing)} to run the live SinoTrade test")
    # One login for all symbols; each login takes a few seconds.
    snapshots = sinotrade.get_sinotrade_snapshots(LIVE_SYMBOLS)
    return {snapshot.code: snapshot for snapshot in snapshots}


@pytest.mark.parametrize('symbol', LIVE_SYMBOLS)
def test_live_snapshot(live_snapshots, symbol):
    snapshot = live_snapshots[symbol]
    print(f"{snapshot.exchange}.{snapshot.code} close={snapshot.close} change={snapshot.change_price} "
          f"buy={snapshot.buy_price} sell={snapshot.sell_price} ts={snapshot.ts}")

    assert str(snapshot.exchange).endswith('TSE')
    assert snapshot.close > 0
    assert snapshot.high >= snapshot.low > 0
    # main.py returns snapshot_to_quote() in the HTTP response, so it must be JSON-serializable.
    quote = json.loads(json.dumps(sinotrade.snapshot_to_quote(snapshot)))
    assert (quote['symbol'], quote['currency']) == (symbol, 'TWD')
    assert quote['previous-close'] > 0
    assert quote['trade-time'].endswith('Z')
