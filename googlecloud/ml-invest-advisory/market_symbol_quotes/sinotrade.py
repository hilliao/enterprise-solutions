import contextlib
import os
import tempfile
import threading
from collections.abc import Generator, Sequence

import shioaji as sj
import yaml

from gcp_data_access import get_gcp_secret
from structured_logging import log, LOG_SEVERITY_DEBUG

# Secret Manager secret in $PROJECT_ID with SinoTrade API keys keyed by Taiwan national ID, in the format:
# A123456789:
#   api_key: ...
#   api_key_secret: ...
SINOTRADE_API_KEY_SECRET_NAME = 'sinotrade-api-key'
# Secret Manager secret with the CA certificate (.pfx) that production orders need; market data doesn't.
SINOTRADE_CA_PFX_SECRET_NAME = 'sinotrade-ca-pfx'
DEFAULT_STOCK_SYMBOLS = ('2330', '006208', '00662')

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

        Use snapshot_to_dict() for a JSON-serializable dict.

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


def snapshot_to_dict(snapshot) -> dict:
    """Converts a shioaji Snapshot to a JSON-serializable dict; enums such as tick_type become their values."""
    return {field: getattr(value, 'value', value) for field, value in snapshot.dict().items()}


if __name__ == "__main__":
    for snapshot in get_sinotrade_snapshots():
        print(f"{snapshot.exchange}.{snapshot.code} has current buy price at {snapshot.buy_price}")

    # The second call uses the cached API key.
    print(snapshot_to_dict(get_sinotrade_snapshots(['2330'])[0]))

    # List the account's stock positions.
    print(get_stock_positions())
