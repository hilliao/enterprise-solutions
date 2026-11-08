"""
Unit tests for the HTTP entry points in main.py. SinoTrade, Alpaca and the Metadata Server are mocked:

    python -m pytest -v test_main.py
"""
import json
from unittest import mock

import flask
import pytest
import requests
from alpaca.common.exceptions import APIError as AlpacaApiError

import main


def make_request(query_string: str = '', method: str = 'GET') -> flask.Request:
    return flask.Request.from_values(query_string=query_string, method=method)


@pytest.fixture(autouse=True)
def not_on_cloud_run(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)


@pytest.fixture
def sinotrade_quotes(monkeypatch):
    get_quotes = mock.Mock(side_effect=lambda symbols: ({s: {'symbol': s, 'price': 1.0} for s in symbols}, []))
    monkeypatch.setattr(main, 'get_sinotrade_quotes', get_quotes)
    return get_quotes


@pytest.fixture
def alpaca_quotes(monkeypatch):
    get_quotes = mock.Mock(return_value=({'VOO': {'price': 1.0}}, {}))
    monkeypatch.setattr(main.alpaca_quotes, 'get_alpaca_realtime_quotes', get_quotes)
    return get_quotes


# get_tw_ticker_quotes

@pytest.mark.parametrize('query_string', ['symbols=2330, 006208,,', 'tickers=2330,006208'])
def test_tw_quotes_returns_quotes_keyed_by_symbol(sinotrade_quotes, query_string):
    body, status, headers = main.get_tw_ticker_quotes(make_request(query_string))

    assert status == 200
    assert body == {'2330': {'symbol': '2330', 'price': 1.0}, '006208': {'symbol': '006208', 'price': 1.0}}
    assert headers == {}
    sinotrade_quotes.assert_called_once_with(['2330', '006208'])


def test_tw_quotes_puts_symbol_errors_in_header(sinotrade_quotes):
    errors = [{'symbol': 'NOPE99', 'error': 'SinoTrade has no contract for the symbol'}]
    sinotrade_quotes.side_effect = None
    sinotrade_quotes.return_value = ({'2330': {'symbol': '2330'}}, errors)

    body, status, headers = main.get_tw_ticker_quotes(make_request('symbols=2330,NOPE99'))

    assert (body, status) == ({'2330': {'symbol': '2330'}}, 200)
    assert json.loads(headers['X-SinoTrade-Errors']) == errors


@pytest.mark.parametrize('query_string, error', [
    ('', 'Missing "symbols" query parameter.'),
    ('symbol=2330', 'Missing "symbols" query parameter.'),
    ('symbols=, ,', 'No valid stock symbols provided.'),
])
def test_tw_quotes_without_symbols_returns_400(sinotrade_quotes, query_string, error):
    assert main.get_tw_ticker_quotes(make_request(query_string)) == ({'error': error}, 400)
    sinotrade_quotes.assert_not_called()


def test_tw_quotes_post_returns_405(sinotrade_quotes):
    assert main.get_tw_ticker_quotes(make_request('symbols=2330', 'POST')) == ({'error': 'Invalid request method.'}, 405)


def test_tw_quotes_sinotrade_failure_returns_500(sinotrade_quotes):
    sinotrade_quotes.side_effect = KeyError('TW_NATIONAL_ID')

    assert main.get_tw_ticker_quotes(make_request('symbols=2330')) == ({'error': "'TW_NATIONAL_ID'"}, 500)


# get_us_ticker_quotes

@pytest.mark.parametrize('query_string', ['symbols=VOO', 'tickers=VOO', 'symbols= VOO ,'])
def test_us_quotes_reads_symbols_or_tickers(alpaca_quotes, query_string):
    assert main.get_us_ticker_quotes(make_request(query_string)) == ({'VOO': {'price': 1.0}}, 200, {})
    alpaca_quotes.assert_called_once_with(tickers=['VOO'])


def test_us_quotes_puts_symbol_errors_in_header(alpaca_quotes):
    alpaca_quotes.return_value = ({'VOO': {'price': 1.0}}, {'XYZ': 'no snapshot'})

    body, status, headers = main.get_us_ticker_quotes(make_request('tickers=VOO,XYZ'))

    assert (body, status) == ({'VOO': {'price': 1.0}}, 200)
    assert json.loads(headers['X-Alpaca-Errors']) == {'XYZ': 'no snapshot'}


@pytest.mark.parametrize('query_string, error', [
    ('', 'Missing "symbols" query parameter.'),
    ('tickers=,', 'No valid stock symbols provided.'),
])
def test_us_quotes_without_symbols_returns_400(alpaca_quotes, query_string, error):
    assert main.get_us_ticker_quotes(make_request(query_string)) == ({'error': error}, 400)
    alpaca_quotes.assert_not_called()


def test_us_quotes_post_returns_405(alpaca_quotes):
    assert main.get_us_ticker_quotes(make_request('tickers=VOO', 'POST')) == ({'error': 'Invalid request method.'}, 405)


def test_us_quotes_alpaca_api_error_returns_500(alpaca_quotes):
    http_error = requests.HTTPError(response=mock.Mock(status_code=403))
    alpaca_quotes.side_effect = AlpacaApiError('{"message": "forbidden"}', http_error)

    body, status = main.get_us_ticker_quotes(make_request('tickers=VOO'))

    assert status == 500
    assert body['error'] == 'Alpaca API returned 403'


def test_us_quotes_unexpected_error_returns_500(alpaca_quotes):
    alpaca_quotes.side_effect = RuntimeError('boom')

    assert main.get_us_ticker_quotes(make_request('tickers=VOO')) == ({'error': 'boom'}, 500)


# Project ID from the Metadata Server on Cloud Run

@pytest.fixture
def on_cloud_run_without_project_id(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'get-tw-ticker-quotes')
    # setenv before delenv so monkeypatch removes the PROJECT_ID that main.py sets when the test ends.
    monkeypatch.setenv('PROJECT_ID', 'unused')
    monkeypatch.delenv('PROJECT_ID')


def test_cloud_run_sets_project_id_from_metadata_server_once(on_cloud_run_without_project_id, sinotrade_quotes):
    metadata_response = mock.Mock(text='my-project\n')
    with mock.patch.object(main.requests, 'get', return_value=metadata_response) as requests_get:
        main.get_tw_ticker_quotes(make_request('symbols=2330'))
        main.get_tw_ticker_quotes(make_request('symbols=2330'))

    assert main.os.environ['PROJECT_ID'] == 'my-project'
    requests_get.assert_called_once()
    assert requests_get.call_args.kwargs['headers'] == {'Metadata-Flavor': 'Google'}


def test_cloud_run_unreachable_metadata_server_leaves_project_id_unset(on_cloud_run_without_project_id,
                                                                        sinotrade_quotes):
    with mock.patch.object(main.requests, 'get', side_effect=requests.ConnectionError('unreachable')):
        body, status, headers = main.get_tw_ticker_quotes(make_request('symbols=2330'))

    assert status == 200
    assert 'PROJECT_ID' not in main.os.environ


def test_local_run_does_not_call_metadata_server(sinotrade_quotes):
    with mock.patch.object(main.requests, 'get') as requests_get:
        main.get_tw_ticker_quotes(make_request('symbols=2330'))

    requests_get.assert_not_called()


def test_project_id_from_metadata_is_none_when_server_unreachable():
    with mock.patch.object(main.requests, 'get', side_effect=requests.ConnectionError('unreachable')):
        assert main.get_project_id_from_metadata() is None
