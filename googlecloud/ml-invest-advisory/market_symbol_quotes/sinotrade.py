import contextlib
import datetime
import json
import os
import tempfile
import threading
from collections.abc import Generator, Sequence
from zoneinfo import ZoneInfo

import shioaji as sj
import yaml

from gcp_data_access import get_gcp_secret
from structured_logging import log, LOG_SEVERITY_DEBUG, LOG_SEVERITY_WARNING

# Secret Manager secret in $PROJECT_ID with SinoTrade API keys keyed by Taiwan national ID, in the format:
# A123456789:
#   api_key: ...
#   api_key_secret: ...
SINOTRADE_API_KEY_SECRET_NAME = 'sinotrade-api-key'
# Secret Manager secret with the CA certificate (.pfx) that production orders need; market data doesn't.
SINOTRADE_CA_PFX_SECRET_NAME = 'sinotrade-ca-pfx'
DEFAULT_STOCK_SYMBOLS = ('2330', '006208', '00662')
# Snapshot timestamps are Taiwan wall-clock time encoded as nanoseconds since the epoch.
TAIWAN_TIME_ZONE = ZoneInfo('Asia/Taipei')

# API keys from SINOTRADE_API_KEY_SECRET_NAME, read on first use. Guarded by sinotrade_api_keys_lock.
sinotrade_api_keys = None
sinotrade_api_keys_lock = threading.Lock()


def get_sinotrade_api_key(secret_id: str = SINOTRADE_API_KEY_SECRET_NAME) -> dict:
    """Reads the SinoTrade API keys, keyed by Taiwan national ID, from a Secret Manager secret in YAML."""
    secret_yaml = get_gcp_secret(secret_id).data.decode("UTF-8")
    try:
        return yaml.safe_load(secret_yaml)
    except yaml.YAMLError as error:
        raise ValueError(f"Secret {secret_id} is not valid YAML.") from error


def get_sinotrade_ca_pfx(secret_id: str = SINOTRADE_CA_PFX_SECRET_NAME):
    """
    Saves the SinoTrade CA certificate from Secret Manager to a temporary .pfx file.

    Returns:
        The file's path and the open temporary file; the file is deleted when the temporary file is closed or
        garbage collected, so keep a reference while the path is in use.
    """
    temp_file = tempfile.NamedTemporaryFile(delete=True, suffix=".pfx")
    temp_file.write(get_gcp_secret(secret_id).data)
    temp_file.flush()
    return temp_file.name, temp_file


def get_cached_sinotrade_api_key() -> dict:
    """Returns the api_key and api_key_secret for $TW_NATIONAL_ID; the secret is read once per process."""
    global sinotrade_api_keys

    with sinotrade_api_keys_lock:
        if sinotrade_api_keys is None:
            sinotrade_api_keys = get_sinotrade_api_key()
            log(text=f"Read SinoTrade API keys from secret {SINOTRADE_API_KEY_SECRET_NAME}.",
                severity=LOG_SEVERITY_DEBUG)
    return sinotrade_api_keys[os.environ['TW_NATIONAL_ID']]


@contextlib.contextmanager
def sinotrade_session(simulation: bool) -> Generator[sj.Shioaji, None, None]:
    """
    Logs in to SinoTrade with the API key for $TW_NATIONAL_ID and logs out on exit. Each login holds one of the
    5 connections SinoTrade allows per national ID until logout, so don't keep sessions open between requests.
    """
    api_key = get_cached_sinotrade_api_key()
    api = sj.Shioaji(simulation=simulation)
    api.login(api_key=api_key['api_key'], secret_key=api_key['api_key_secret'])
    try:
        yield api
    finally:
        api.logout()


def get_stock_positions():
    """
    Lists the current positions, in shares, of the production stock account for $TW_NATIONAL_ID.
    TODO: change the argument to accept a list of API key, secret.

    Covers only Taiwan stocks. It can't list US holdings: they sit in the 複委託 (sub-brokerage) account, type H in
    api.list_accounts(), and sinotrade.com.tw doesn't support getting positions in an H account. Calling
    api.list_positions(account=<the H account>) fails with ServerError code 406, "Account Not Acceptable".

    Returns:
        A list of shioaji StockPosition objects, one per held stock, with the code, direction, quantity in shares,
        average cost price and unrealized pnl in TWD. For example, with illustrative values:

        [StockPosition(code=2330, direction=<Action.Buy: 'Buy'>, quantity=10, price=1000.0, pnl=5000)]
    """
    with sinotrade_session(simulation=False) as api:
        return api.list_positions(api.stock_account, unit=sj.Unit.Share)


def get_sinotrade_snapshots(stock_symbols: Sequence[str] = DEFAULT_STOCK_SYMBOLS):
    """
    Gets current quote snapshots for Taiwan stocks and ETFs from the SinoTrade (Shioaji) simulation server.
    Simulation mode serves market data without a CA certificate and can't place orders.

    Environment variables:
        PROJECT_ID: Google Cloud project that holds the "sinotrade-api-key" secret; read by gcp_data_access.py.
            main.py sets it from the Metadata Server on Cloud Run; set it yourself when running locally.
        TW_NATIONAL_ID: Taiwan national ID that keys the api_key and api_key_secret in the secret's YAML.

    The caller needs roles/secretmanager.secretAccessor on the secret, e.g. Application Default Credentials from
    `gcloud auth application-default login` when running locally. The secret is read once per process.

    Args:
        stock_symbols: Taiwan stock codes such as 2330 (TSMC) or 006208 (Fubon Taiwan 50 ETF).

    Returns:
        A list of shioaji Snapshot objects, one per symbol, with fields such as code, exchange, close, high, low,
        change_price, buy_price, sell_price and ts (nanoseconds since the epoch, in Taiwan time). For example,
        get_sinotrade_snapshots(['2330']) after the close on Friday 2026-11-06 returned:

        [Snapshot(ts=1793975400000000000, code='2330', exchange='TSE', open=2020, high=2195, low=2020, close=2135,
                  tick_type=<TickType.Sell: 'Sell'>, change_price=-105, change_rate=-4.68,
                  change_type=<ChangeType.Down: 'Down'>, average_price=2093.18, volume=106, total_volume=97065,
                  amount=226310000, total_amount=203179565000, yesterday_volume=36585, buy_price=2135,
                  buy_volume=12, sell_price=2140, sell_volume=1039, volume_ratio=2.65)]

        Use snapshot_to_quote() for a JSON-serializable quote, or get_sinotrade_quotes() to skip unknown symbols.

    Raises:
        KeyError: PROJECT_ID or TW_NATIONAL_ID isn't set, TW_NATIONAL_ID isn't a key in the secret, or a symbol
            isn't a known contract.
    """
    with sinotrade_session(simulation=True) as api:
        contracts = []
        for symbol in stock_symbols:
            contract = api.contracts.get(symbol)
            if contract is None:
                raise KeyError(symbol)
            contracts.append(contract)
        return api.snapshots(contracts)


def snapshot_time_to_utc(ts: int) -> datetime.datetime:
    """
    Converts a snapshot's ts, Taiwan wall-clock time as nanoseconds since the epoch, to a UTC datetime, e.g.
    1793975400000000000 (2026-11-06 14:30 in Taipei, the end of the after-hours session) returns
    2026-11-06 06:30:00+00:00.
    """
    taiwan_time = datetime.datetime.fromtimestamp(ts / 1e9, datetime.timezone.utc).replace(tzinfo=TAIWAN_TIME_ZONE)
    return taiwan_time.astimezone(datetime.timezone.utc)


def snapshot_to_quote(snapshot) -> dict:
    """
    Converts a shioaji Snapshot to a quote with the same keys as the US quotes in alpaca-quotes.py, e.g. for 2330
    after the close on Friday 2026-11-06:
    {
      "symbol": "2330", "price": 2135.0, "previous-close": 2240.0, "net-change": -105.0, "net-change-%": -4.68,
      "trade-time": "2026-11-06T06:30:00Z", "open": 2020.0, "high": 2195.0, "low": 2020.0, "bid": 2135.0,
      "ask": 2140.0, "currency": "TWD"
    }
    price is the snapshot's close, the latest trade price; previous-close is price - net-change. Prices are in TWD.
    Unlike the US quotes there is no close, which would equal price, and no volume, whose unit Shioaji doesn't
    document.
    """
    price = float(snapshot.close)
    net_change = float(snapshot.change_price)
    return {
        'symbol': snapshot.code,
        'price': price,
        'previous-close': round(price - net_change, 4),
        'net-change': round(net_change, 4),
        'net-change-%': round(float(snapshot.change_rate), 2),
        'trade-time': snapshot_time_to_utc(snapshot.ts).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'open': float(snapshot.open),
        'high': float(snapshot.high),
        'low': float(snapshot.low),
        'bid': float(snapshot.buy_price),
        'ask': float(snapshot.sell_price),
        'currency': 'TWD',
    }


def get_sinotrade_quotes(stock_symbols: Sequence[str]) -> tuple[dict, list]:
    """
    Gets quotes for Taiwan stocks and ETFs from the SinoTrade simulation server, skipping unknown symbols. Needs the
    environment variables and permissions described in get_sinotrade_snapshots().

    Args:
        stock_symbols: Taiwan stock codes, e.g. ["2330", "006208", "NOPE99"]; upper-cased and de-duplicated.

    Returns:
        A tuple of (symbol_quotes, symbol_errors). symbol_quotes maps each known symbol to its snapshot_to_quote(),
        e.g. {"2330": {"symbol": "2330", "price": 2135.0, ...}, "006208": {...}}. symbol_errors lists the unknown
        symbols, e.g. [{"symbol": "NOPE99", "error": "SinoTrade has no contract for the symbol"}].
    """
    symbols = list(dict.fromkeys(symbol.upper() for symbol in stock_symbols))
    symbol_errors = []
    with sinotrade_session(simulation=True) as api:
        contracts = []
        for symbol in symbols:
            contract = api.contracts.get(symbol)
            if contract is None:
                symbol_errors.append({'symbol': symbol, 'error': 'SinoTrade has no contract for the symbol'})
            else:
                contracts.append(contract)
        snapshots = api.snapshots(contracts) if contracts else []

    symbol_quotes = {snapshot.code: snapshot_to_quote(snapshot) for snapshot in snapshots}
    if symbol_errors:
        log(text=f"SinoTrade quote errors: {json.dumps(symbol_errors)}", severity=LOG_SEVERITY_WARNING)
    return symbol_quotes, symbol_errors


if __name__ == "__main__":
    for snapshot in get_sinotrade_snapshots():
        print(f"{snapshot.exchange}.{snapshot.code} has current buy price at {snapshot.buy_price}")

    # The second call uses the cached API key.
    print(get_sinotrade_quotes(['2330', 'NOPE99']))

    # List the account's stock positions.
    print(get_stock_positions())
