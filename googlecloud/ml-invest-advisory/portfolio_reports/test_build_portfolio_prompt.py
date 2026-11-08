"""
Unit tests for build_portfolio_prompt.py. The stock quotes Cloud Run service, Google ID tokens and SEC EDGAR are
mocked, and SEC files are cached in a temporary folder:

    python -m pytest -v test_build_portfolio_prompt.py
"""
import json
import os
from unittest import mock

import pytest
import requests

import build_portfolio_prompt as bpp

QUOTES_URL = 'https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes'
TW_QUOTES_URL = 'https://us-central1-my-gcp-project.cloudfunctions.net/get-tw-ticker-quotes'
# Quotes after the close on Friday 2026-11-06, in the get-us-ticker-quotes format.
VOO_QUOTE = {'symbol': 'VOO', 'price': 675.9, 'previous-close': 673.94, 'net-change': 1.96, 'net-change-%': 0.29,
             'trade-time': '2026-11-06T21:00:03Z', 'open': 675.435, 'high': 681.44, 'low': 675.34, 'close': 676.02,
             'volume': 109275.0, 'bid': 655.12, 'ask': 696.49}
AAAU_QUOTE = {'symbol': 'AAAU', 'price': 39.41, 'previous-close': 39.675, 'net-change': -0.265, 'net-change-%': -0.67}
TSMC_QUOTE = {'symbol': '2330', 'price': 2135.0, 'previous-close': 2240.0, 'net-change': -105.0, 'net-change-%': -4.68,
              'trade-time': '2026-11-06T06:30:00Z', 'open': 2020.0, 'high': 2195.0, 'low': 2020.0, 'bid': 2135.0,
              'ask': 2140.0, 'currency': 'TWD'}
# Units of TWD per USD from open.er-api.com on 2026-11-08.
TWD_PER_USD = 32.847015


def http_error(status_code: int, body) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    response.reason = 'Internal Server Error'
    response.url = f"{QUOTES_URL}/?tickers=VOO"
    response._content = (json.dumps(body) if isinstance(body, dict) else body).encode()
    return requests.HTTPError(f"{status_code} Server Error: Internal Server Error for url: {response.url}",
                              response=response)


# Terminal output

def test_condensed_json_prints_first_keys_and_count_of_the_rest():
    data = {'AAAU': {'shares': 1215.0}, 'BIL': {'shares': 65.0}, 'NVDA': {'shares': 1.0}}

    assert bpp.condensed_json(data, 2) == '{\n  "AAAU": {"shares": 1215.0},\n  "BIL": {"shares": 65.0},\n  ... 1 more\n}'
    assert json.loads(bpp.condensed_json(data, 3)) == data
    assert bpp.condensed_json([1, 2], 1) == '[1, 2]'


def test_describe_request_failure_pretty_prints_json_body():
    error = http_error(500, {'error': 'Alpaca API returned 403', 'detail': '{"message": "forbidden."}'})

    description = bpp.describe_request_failure(error)

    assert description.startswith(f"500 Server Error: Internal Server Error for url: {QUOTES_URL}/?tickers=VOO\n"
                                  "Response status: 500\nResponse body:\n{\n")
    assert '  "error": "Alpaca API returned 403",' in description


def test_describe_request_failure_without_response():
    assert bpp.describe_request_failure(requests.ConnectTimeout('timed out')) == 'timed out'


# Portfolio file

def test_load_portfolio_separates_cash(tmp_path):
    portfolio_file = tmp_path / 'portfolio.json'
    portfolio_file.write_text(json.dumps({'NVDA': {'shares': 2050.0}, 'BIL': {'shares': 634.0},
                                          '__CASH': {'shares': 492.08}}))

    assert bpp.load_portfolio(str(portfolio_file)) == ({'NVDA': {'shares': 2050.0}, 'BIL': {'shares': 634.0}}, 492.08)


def test_load_portfolio_without_cash(tmp_path):
    portfolio_file = tmp_path / 'portfolio.json'
    portfolio_file.write_text(json.dumps({'NVDA': {'shares': 1}}))

    assert bpp.load_portfolio(str(portfolio_file)) == ({'NVDA': {'shares': 1}}, 0.0)


# Stock quotes

@pytest.fixture
def no_retry_sleep(monkeypatch):
    sleep = mock.Mock()
    monkeypatch.setattr(bpp.time, 'sleep', sleep)
    return sleep


@pytest.fixture
def id_token(monkeypatch):
    fetch_id_token = mock.Mock(return_value='id-token')
    monkeypatch.setattr(bpp.id_token, 'fetch_id_token', fetch_id_token)
    return fetch_id_token


def test_get_cloud_run_response_sends_id_token_for_audience(id_token, no_retry_sleep):
    response = mock.Mock(text='{"VOO": {}}')
    with mock.patch.object(bpp.requests, 'get', return_value=response) as requests_get:
        assert bpp.get_cloud_run_response(QUOTES_URL, f"{QUOTES_URL}/?tickers=VOO") == '{"VOO": {}}'

    assert id_token.call_args.args[1] == QUOTES_URL
    assert requests_get.call_args.kwargs['headers'] == {'Authorization': 'Bearer id-token'}
    no_retry_sleep.assert_not_called()


def test_get_cloud_run_response_retries_with_backoff_then_succeeds(id_token, no_retry_sleep):
    success = mock.Mock(text='{}')
    with mock.patch.object(bpp.requests, 'get', side_effect=[requests.ConnectionError('down'),
                                                             requests.ConnectionError('down'), success]):
        assert bpp.get_cloud_run_response(QUOTES_URL, QUOTES_URL) == '{}'

    assert [c.args[0] for c in no_retry_sleep.call_args_list] == [1, 2]


def test_get_cloud_run_response_gives_up_after_last_retry(id_token, no_retry_sleep):
    with mock.patch.object(bpp.requests, 'get', side_effect=requests.ConnectionError('down')) as requests_get:
        with pytest.raises(requests.ConnectionError):
            bpp.get_cloud_run_response(QUOTES_URL, QUOTES_URL)

    assert requests_get.call_count == len(bpp.CLOUD_RUN_RETRY_DELAYS) + 1
    assert [c.args[0] for c in no_retry_sleep.call_args_list] == bpp.CLOUD_RUN_RETRY_DELAYS


def test_get_with_retries_returns_response_without_headers(no_retry_sleep):
    response = mock.Mock()
    with mock.patch.object(bpp.requests, 'get', side_effect=[requests.Timeout('slow'), response]) as requests_get:
        assert bpp.get_with_retries(bpp.USD_EXCHANGE_RATES_URL, timeout=5) is response

    assert requests_get.call_args.kwargs == {'headers': None, 'timeout': 5}


@pytest.fixture
def quotes_env(monkeypatch):
    monkeypatch.setenv('STOCK_QUOTES_CLOUD_RUN_URL', QUOTES_URL)
    monkeypatch.setenv('TW_STOCK_QUOTES_CLOUD_RUN_URL', TW_QUOTES_URL)
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/path/to/key.json')


def test_fetch_stock_quotes_requests_tickers_and_parses_json(quotes_env, monkeypatch):
    get_response = mock.Mock(return_value=json.dumps({'VOO': VOO_QUOTE}))
    monkeypatch.setattr(bpp, 'get_cloud_run_response', get_response)

    assert bpp.fetch_stock_quotes(['VOO', 'XYZQ']) == {'VOO': VOO_QUOTE}
    get_response.assert_called_once_with(QUOTES_URL, f"{QUOTES_URL}/?tickers=VOO,XYZQ")


def test_fetch_stock_quotes_sends_tw_tickers_to_tw_service_and_keeps_prefix(quotes_env, monkeypatch):
    responses = {QUOTES_URL: {'VOO': VOO_QUOTE}, TW_QUOTES_URL: {'2330': TSMC_QUOTE}}
    get_response = mock.Mock(side_effect=lambda audience, url: json.dumps(responses[audience]))
    monkeypatch.setattr(bpp, 'get_cloud_run_response', get_response)

    assert bpp.fetch_stock_quotes(['VOO', 'TW:2330', 'TW:NOPE99']) == {'VOO': VOO_QUOTE, 'TW:2330': TSMC_QUOTE}
    assert get_response.call_args_list == [mock.call(QUOTES_URL, f"{QUOTES_URL}/?tickers=VOO"),
                                           mock.call(TW_QUOTES_URL, f"{TW_QUOTES_URL}/?tickers=2330,NOPE99")]


@pytest.mark.parametrize('tickers, unused_url_variable', [
    (['VOO'], 'TW_STOCK_QUOTES_CLOUD_RUN_URL'),
    (['TW:2330'], 'STOCK_QUOTES_CLOUD_RUN_URL'),
])
def test_fetch_stock_quotes_only_needs_url_of_markets_held(quotes_env, monkeypatch, tickers, unused_url_variable):
    monkeypatch.delenv(unused_url_variable)
    get_response = mock.Mock(return_value='{}')
    monkeypatch.setattr(bpp, 'get_cloud_run_response', get_response)

    bpp.fetch_stock_quotes(tickers)

    get_response.assert_called_once()


@pytest.mark.parametrize('missing', ['STOCK_QUOTES_CLOUD_RUN_URL', 'GOOGLE_APPLICATION_CREDENTIALS'])
def test_fetch_stock_quotes_without_environment_variable_exits_1(quotes_env, monkeypatch, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(SystemExit) as exit_info:
        bpp.fetch_stock_quotes(['VOO'])
    assert exit_info.value.code == 1


def test_fetch_stock_quotes_invalid_json_exits_1(quotes_env, monkeypatch):
    monkeypatch.setattr(bpp, 'get_cloud_run_response', mock.Mock(return_value='<html>oops</html>'))

    with pytest.raises(SystemExit) as exit_info:
        bpp.fetch_stock_quotes(['VOO'])
    assert exit_info.value.code == 1


def test_fetch_stock_quotes_unreachable_service_exits_69(quotes_env, monkeypatch):
    monkeypatch.setattr(bpp, 'get_cloud_run_response', mock.Mock(side_effect=requests.ConnectionError('down')))

    with pytest.raises(SystemExit) as exit_info:
        bpp.fetch_stock_quotes(['VOO'])
    assert exit_info.value.code == bpp.EXIT_CODE_QUOTES_UNAVAILABLE


# Exchange rates

@pytest.fixture
def exchange_rates(monkeypatch):
    body = {'result': 'success', 'time_last_update_utc': 'Sun, 08 Nov 2026 00:02:31 +0000', 'base_code': 'USD',
            'rates': {'USD': 1, 'TWD': TWD_PER_USD, 'JPY': 153.1}}
    get_with_retries = mock.Mock(return_value=mock.Mock(json=mock.Mock(return_value=body)))
    monkeypatch.setattr(bpp, 'get_with_retries', get_with_retries)
    return get_with_retries


def test_fetch_local_currency_per_usd(exchange_rates):
    assert bpp.fetch_local_currency_per_usd({'TWD'}) == {'TWD': TWD_PER_USD}
    assert exchange_rates.call_args.args[0] == 'https://open.er-api.com/v6/latest/USD'


def test_fetch_local_currency_per_usd_without_rate_exits_69(exchange_rates):
    with pytest.raises(SystemExit) as exit_info:
        bpp.fetch_local_currency_per_usd({'TWD', 'XYZ'})
    assert exit_info.value.code == bpp.EXIT_CODE_QUOTES_UNAVAILABLE


@pytest.mark.parametrize('failure', [requests.ConnectionError('down'), ValueError('not JSON')])
def test_fetch_local_currency_per_usd_failure_exits_69(monkeypatch, failure):
    monkeypatch.setattr(bpp, 'get_with_retries', mock.Mock(side_effect=failure))

    with pytest.raises(SystemExit) as exit_info:
        bpp.fetch_local_currency_per_usd({'TWD'})
    assert exit_info.value.code == bpp.EXIT_CODE_QUOTES_UNAVAILABLE


def test_convert_quotes_to_usd_converts_prices_only():
    quotes = {'VOO': VOO_QUOTE, 'TW:2330': TSMC_QUOTE}

    converted = bpp.convert_quotes_to_usd(quotes, {'TWD': TWD_PER_USD})

    assert converted['VOO'] == VOO_QUOTE
    tsmc = converted['TW:2330']
    assert tsmc['currency'] == 'USD'
    assert tsmc['price'] == pytest.approx(64.9983, abs=1e-4)
    assert tsmc['previous-close'] == pytest.approx(68.1949, abs=1e-4)
    assert tsmc['bid'] == pytest.approx(2135.0 / TWD_PER_USD)
    assert (tsmc['net-change-%'], tsmc['symbol'], tsmc['trade-time']) == (-4.68, '2330', '2026-11-06T06:30:00Z')
    assert quotes['TW:2330'] == TSMC_QUOTE


def test_quotes_in_usd_without_other_currencies_fetches_no_rates(exchange_rates):
    quotes = {'VOO': VOO_QUOTE}

    assert bpp.quotes_in_usd(quotes) is quotes
    exchange_rates.assert_not_called()


def test_quotes_in_usd_fetches_rates_for_other_currencies(exchange_rates):
    quotes = bpp.quotes_in_usd({'VOO': VOO_QUOTE, 'TW:2330': TSMC_QUOTE})

    assert quotes['TW:2330']['price'] == pytest.approx(2135.0 / TWD_PER_USD)
    exchange_rates.assert_called_once()


# Portfolio values and weights

def test_merge_shares_into_quotes_copies_quotes():
    quotes = {'AAAU': dict(AAAU_QUOTE)}

    merged = bpp.merge_shares_into_quotes({'AAAU': {'shares': 10}, 'XYZQ': {'shares': 1}}, quotes)

    assert merged == {'AAAU': {**AAAU_QUOTE, 'shares': 10}, 'XYZQ': {'shares': 1}}
    assert quotes == {'AAAU': AAAU_QUOTE}


def test_calculate_values_and_weights():
    quotes_with_shares = {'VOO': {**VOO_QUOTE, 'shares': 2}, 'AAAU': {**AAAU_QUOTE, 'shares': 10}}

    assert bpp.calculate_values_and_weights(quotes_with_shares, cash_amount=100.0) == {
        'VOO': {'Current Value': 1351.8, 'Previous Value': 1347.88, 'shares': 2.0,
                'single share change in percentage': '0.29%', 'weight in percentage': '73.23%'},
        'AAAU': {'Current Value': 394.1, 'Previous Value': 396.75, 'shares': 10.0,
                 'single share change in percentage': '-0.67%', 'weight in percentage': '21.35%'},
        '__SUM': {'Current Value': 1845.9, 'Previous Value': 1844.63,
                  'daily performance change in percentage': '0.07%'},
        '__CASH': {'shares': 100.0, 'weight in percentage': '5.42%'},
    }


def test_calculate_values_and_weights_accepts_numeric_strings():
    values = bpp.calculate_values_and_weights({'VOO': {'price': '675.9', 'previous-close': '673.94', 'shares': '2'}})

    assert values['VOO']['Current Value'] == 1351.8
    assert values['VOO']['single share change in percentage'] == '0.00%'


@pytest.mark.parametrize('attributes', [
    {'shares': 1},  # no quote, e.g. an unknown ticker
    {'price': 1.0, 'previous-close': 1.0},  # no shares
    {'price': 'n/a', 'previous-close': 1.0, 'shares': 1},  # not a number
])
def test_calculate_values_and_weights_without_usable_quote_exits_69(attributes):
    with pytest.raises(SystemExit) as exit_info:
        bpp.calculate_values_and_weights({'VOO': {**VOO_QUOTE, 'shares': 2}, 'XYZQ': attributes})
    assert exit_info.value.code == bpp.EXIT_CODE_QUOTES_UNAVAILABLE


# Ticker names

def test_load_ticker_names_file_upper_cases_tickers_and_strips_names(tmp_path):
    names_file = tmp_path / 'ticker_names.json'
    names_file.write_text(json.dumps({'ewt': ' iShares MSCI Taiwan ETF (Taiwanese stocks) '}))

    assert bpp.load_ticker_names_file(str(names_file)) == {'EWT': 'iShares MSCI Taiwan ETF (Taiwanese stocks)'}


@pytest.mark.parametrize('content', ['not json', '["EWT"]', '{"EWT": ""}', '{"EWT": 1}'])
def test_load_ticker_names_file_invalid_returns_empty(tmp_path, content):
    names_file = tmp_path / 'ticker_names.json'
    names_file.write_text(content)

    assert bpp.load_ticker_names_file(str(names_file)) == {}


def test_load_ticker_names_file_missing_returns_empty(tmp_path):
    assert bpp.load_ticker_names_file(str(tmp_path / 'missing.json')) == {}


@pytest.fixture
def sec_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bpp, 'SEC_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(bpp.time, 'sleep', mock.Mock())
    return tmp_path


def test_load_sec_json_downloads_and_caches(sec_cache_dir):
    response = mock.Mock(json=mock.Mock(return_value={'name': 'VANGUARD INDEX FUNDS'}))
    with mock.patch.object(bpp.requests, 'get', return_value=response) as requests_get:
        assert bpp.load_sec_json('https://sec/x.json', 'x.json') == {'name': 'VANGUARD INDEX FUNDS'}
        assert bpp.load_sec_json('https://sec/x.json', 'x.json') == {'name': 'VANGUARD INDEX FUNDS'}

    requests_get.assert_called_once()
    assert 'User-Agent' in requests_get.call_args.kwargs['headers']
    assert json.loads((sec_cache_dir / 'x.json').read_text()) == {'name': 'VANGUARD INDEX FUNDS'}


def test_load_sec_json_uses_stale_cache_when_download_fails(sec_cache_dir):
    cache_file = sec_cache_dir / 'x.json'
    cache_file.write_text('{"name": "cached"}')
    stale_time = cache_file.stat().st_mtime - bpp.SEC_CACHE_MAX_AGE_SECONDS - 1
    os.utime(cache_file, (stale_time, stale_time))

    with mock.patch.object(bpp.requests, 'get', side_effect=requests.ConnectionError('down')):
        assert bpp.load_sec_json('https://sec/x.json', 'x.json') == {'name': 'cached'}


def test_load_sec_json_without_cache_when_download_fails_returns_none(sec_cache_dir):
    with mock.patch.object(bpp.requests, 'get', side_effect=requests.ConnectionError('down')):
        assert bpp.load_sec_json('https://sec/x.json', 'x.json') is None


@pytest.fixture
def sec_files(monkeypatch):
    """Serves SEC EDGAR JSON for NVDA (a company), QQQ (a fund) and BRK-B, without network access."""
    files = {
        'sec_company_tickers.json': {'0': {'cik_str': 1045810, 'ticker': 'NVDA', 'title': 'NVIDIA CORP'},
                                     '1': {'cik_str': 1067983, 'ticker': 'BRK-B', 'title': 'BERKSHIRE HATHAWAY INC'}},
        'sec_company_tickers_mf.json': {'fields': ['cik', 'seriesId', 'classId', 'symbol'],
                                        'data': [[1067839, 'S000101292', 'C000271435', 'QQQ']]},
        'sec_submissions_CIK0001067839.json': {'name': 'INVESCO QQQ TRUST, SERIES 1'},
    }
    load_sec_json = mock.Mock(side_effect=lambda url, cache_file_name: files.get(cache_file_name))
    monkeypatch.setattr(bpp, 'load_sec_json', load_sec_json)
    return load_sec_json


def test_lookup_sec_names_names_companies_and_funds(sec_files):
    assert bpp.lookup_sec_names(['NVDA', 'QQQ', 'BRK.B', 'XYZQ']) == {
        'NVDA': 'NVIDIA CORP', 'QQQ': 'INVESCO QQQ TRUST, SERIES 1', 'BRK.B': 'BERKSHIRE HATHAWAY INC'}


def test_lookup_ticker_names_prefers_ticker_names_file(sec_files, tmp_path):
    names_file = tmp_path / 'ticker_names.json'
    names_file.write_text(json.dumps({'QQQ': 'Invesco QQQ Trust (Nasdaq-100)'}))

    assert bpp.lookup_ticker_names(['QQQ', 'NVDA', 'XYZQ'], str(names_file)) == {
        'QQQ': 'Invesco QQQ Trust (Nasdaq-100)', 'NVDA': 'NVIDIA CORP'}


def test_lookup_ticker_names_skips_sec_for_tw_tickers(sec_files, tmp_path, monkeypatch):
    names_file = tmp_path / 'ticker_names.json'
    names_file.write_text(json.dumps({'TW:2330': 'Taiwan Semiconductor Manufacturing (TSMC)'}))
    lookup_sec_names = mock.Mock(wraps=bpp.lookup_sec_names)
    monkeypatch.setattr(bpp, 'lookup_sec_names', lookup_sec_names)

    assert bpp.lookup_ticker_names(['TW:2330', 'TW:006208', 'NVDA'], str(names_file)) == {
        'TW:2330': 'Taiwan Semiconductor Manufacturing (TSMC)', 'NVDA': 'NVIDIA CORP'}
    lookup_sec_names.assert_called_once_with(['NVDA'])


def test_add_ticker_names_puts_name_first_and_skips_totals(sec_files, tmp_path):
    values_by_ticker = {'NVDA': {'Current Value': 1.0}, 'XYZQ': {'Current Value': 2.0},
                        '__SUM': {'Current Value': 3.0}, '__CASH': {'shares': 0}}

    named = bpp.add_ticker_names(values_by_ticker, str(tmp_path / 'missing.json'))

    assert list(named['NVDA']) == ['Name', 'Current Value']
    assert named['NVDA']['Name'] == 'NVIDIA CORP'
    assert named['XYZQ'] == {'Current Value': 2.0}
    assert named['__SUM'] == {'Current Value': 3.0} and named['__CASH'] == {'shares': 0}


# LLM prompt

def test_write_prompt_replaces_placeholder(tmp_path):
    template = tmp_path / 'template.txt'
    template.write_text('Holdings:\n{{PORTFOLIO_HOLDING_DATA_JSON}}\nEnd')
    output = tmp_path / 'prompt.txt'

    bpp.write_prompt(str(template), {'VOO': {'shares': 2.0}}, str(output))

    assert output.read_text() == 'Holdings:\n{\n  "VOO": {\n    "shares": 2.0\n  }\n}\nEnd'


@pytest.mark.parametrize('output_prompt, expected', [
    ('prompt.txt', os.path.join('prompt_templates', 'prompt.txt')),
    ('/tmp/out.txt', '/tmp/out.txt'),
])
def test_output_prompt_path(output_prompt, expected):
    assert bpp.output_prompt_path(output_prompt, 'prompt_templates/daily_report_prompt_template.txt') == expected


def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr('sys.argv', ['build_portfolio_prompt.py', '--portfolio_file', 'portfolios/vicky.json',
                                     '--llm_prompt_template', 'prompt_templates/daily_report_prompt_template.txt'])

    args = bpp.parse_args()

    assert (args.output_prompt, args.ticker_names_file) == ('prompt.txt', bpp.DEFAULT_TICKER_NAMES_FILE)


def test_main_writes_prompt(tmp_path, monkeypatch, sec_files):
    portfolio_file = tmp_path / 'portfolio.json'
    portfolio_file.write_text(json.dumps({'VOO': {'shares': 2}, 'AAAU': {'shares': 10}, '__CASH': {'shares': 100.0}}))
    template = tmp_path / 'template.txt'
    template.write_text('{{PORTFOLIO_HOLDING_DATA_JSON}}')
    names_file = tmp_path / 'ticker_names.json'
    names_file.write_text(json.dumps({'VOO': 'Vanguard S&P 500 ETF (S&P 500)'}))
    monkeypatch.setattr('sys.argv', ['build_portfolio_prompt.py', '--portfolio_file', str(portfolio_file),
                                     '--llm_prompt_template', str(template), '--ticker_names_file', str(names_file)])
    monkeypatch.setattr(bpp, 'fetch_stock_quotes', mock.Mock(return_value={'VOO': VOO_QUOTE, 'AAAU': AAAU_QUOTE}))

    bpp.main()

    prompt_data = json.loads((tmp_path / 'prompt.txt').read_text())
    assert prompt_data['VOO']['Name'] == 'Vanguard S&P 500 ETF (S&P 500)'
    assert prompt_data['__SUM']['daily performance change in percentage'] == '0.07%'
    bpp.fetch_stock_quotes.assert_called_once_with(['VOO', 'AAAU'])


def test_main_values_tw_holdings_in_usd(tmp_path, monkeypatch, sec_files, exchange_rates):
    portfolio_file = tmp_path / 'portfolio.json'
    portfolio_file.write_text(json.dumps({'VOO': {'shares': 2}, 'TW:2330': {'shares': 1000}}))
    template = tmp_path / 'template.txt'
    template.write_text('{{PORTFOLIO_HOLDING_DATA_JSON}}')
    monkeypatch.setattr('sys.argv', ['build_portfolio_prompt.py', '--portfolio_file', str(portfolio_file),
                                     '--llm_prompt_template', str(template),
                                     '--ticker_names_file', str(tmp_path / 'missing.json')])
    monkeypatch.setattr(bpp, 'fetch_stock_quotes', mock.Mock(return_value={'VOO': VOO_QUOTE, 'TW:2330': TSMC_QUOTE}))

    bpp.main()

    prompt_data = json.loads((tmp_path / 'prompt.txt').read_text())
    # 1000 shares of 2330 at 2135 TWD is 2135000 / 32.847015 = 64998.30 USD.
    assert prompt_data['TW:2330']['Current Value'] == 64998.3
    assert prompt_data['TW:2330']['single share change in percentage'] == '-4.68%'
    assert prompt_data['__SUM']['Current Value'] == round(1351.8 + 2135000 / TWD_PER_USD, 2)
