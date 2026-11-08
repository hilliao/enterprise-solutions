"""
Tests for sinotrade.get_sinotrade_snapshots().

The offline tests mock Shioaji and Secret Manager. The live test logs in to the SinoTrade simulation server
with the API key in the "sinotrade-api-key" secret; it runs only when PROJECT_ID and TW_NATIONAL_ID are set
and Application Default Credentials can read that secret:

    gcloud auth application-default login
    PROJECT_ID=... TW_NATIONAL_ID=... python -m pytest -v test_sinotrade.py
"""
import json
import os
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


def test_snapshot_to_dict_replaces_enums_with_values():
    snapshot = mock.Mock()
    snapshot.dict.return_value = {'code': '2330', 'close': 2135.0, 'tick_type': sj.TickType.Sell}

    assert sinotrade.snapshot_to_dict(snapshot) == {'code': '2330', 'close': 2135.0, 'tick_type': 'Sell'}


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
    # main.py returns snapshot_to_dict() in the HTTP response, so it must be JSON-serializable.
    assert json.loads(json.dumps(sinotrade.snapshot_to_dict(snapshot)))['code'] == symbol
