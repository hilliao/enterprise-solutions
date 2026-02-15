import os
import tempfile
import shioaji as sj
import yaml

from gcp_data_access import get_gcp_secret


def get_sinotrade_api_key(secret_id: str = "sinotrade-api-key"):
    """
    Accesses a secret's payload from Google Cloud Secret Manager.
    """
    payload = get_gcp_secret(secret_id)
    # Decode the payload to yaml.
    sino_trade_api_yaml = payload.data.decode("UTF-8")

    try:
        sino_trade_api_dict = yaml.safe_load(sino_trade_api_yaml)
        return sino_trade_api_dict
    except yaml.YAMLError as e:
        raise ValueError("Secret payload is not valid YAML format.") from e


def get_sinotrade_ca_pfx(secret_id: str = "sinotrade-ca-pfx"):
    """
    Accesses the Sinotrade CA PFX file from Google Cloud Secret Manager
    and saves it to a temporary file.
    """
    payload = get_gcp_secret(secret_id)
    # The payload is the binary content of the PFX file
    pfx_content = payload.data

    # Save the PFX content to a temporary file
    # Use tempfile to create a temporary file that will be automatically deleted
    temp_file = tempfile.NamedTemporaryFile(delete=True, suffix=".pfx")
    temp_pfx_path = temp_file.name
    with open(temp_pfx_path, "wb") as f:
        f.write(pfx_content)
    return temp_pfx_path, temp_file


_cached_sinotrade_api_key_yaml = None
_cached_temp_pfx_path = None
_cached_temp_file_obj = None


def get_stock_positions():
    """
    Lists current positions for the stock account where API key is cached.
    TODO: change the argument to accept a list of API key, secret.

    Returns:
        List of current stock positions
    """
    global _cached_sinotrade_api_key_yaml, _cached_temp_pfx_path, _cached_temp_file_obj

    if _cached_sinotrade_api_key_yaml is None:
        _cached_sinotrade_api_key_yaml = get_sinotrade_api_key()
        print("Successfully cached SinoTrade API key from Secret Manager.")
    else:
        print("Using cached SinoTrade API key.")

    api = sj.Shioaji(simulation=False)
    tw_national_id = os.environ['TW_NATIONAL_ID']
    accounts = api.login(api_key=_cached_sinotrade_api_key_yaml[tw_national_id]['api_key'],
                         secret_key=_cached_sinotrade_api_key_yaml[tw_national_id]['api_key_secret'])

    positions = api.list_positions(api.stock_account, unit=sj.constant.Unit.Share)
    return positions


def get_sinotrade_snapshots(stock_symbols: list = ['2330', '006208', '00662']):
    global _cached_sinotrade_api_key_yaml, _cached_temp_pfx_path, _cached_temp_file_obj

    if _cached_sinotrade_api_key_yaml is None:
        _cached_sinotrade_api_key_yaml = get_sinotrade_api_key()
        print("Successfully cached SinoTrade API key from Secret Manager.")
    else:
        print("Using cached SinoTrade API key.")

    api = sj.Shioaji(simulation=True)
    tw_national_id = os.environ['TW_NATIONAL_ID']
    accounts = api.login(api_key=_cached_sinotrade_api_key_yaml[tw_national_id]['api_key'],
                         secret_key=_cached_sinotrade_api_key_yaml[tw_national_id]['api_key_secret'])
    
    contracts = [api.Contracts.Stocks[symbol] for symbol in stock_symbols]
    snapshots = api.snapshots(contracts)
    return snapshots


if __name__ == "__main__":
    snapshots = get_sinotrade_snapshots()
    for element in snapshots:
        print(f"{element['exchange']}.{element['code']} "
              f"has current buy price at "
              f"{element['buy_price']}")

    # test cached Sinotrade API key, secret
    snapshots = get_sinotrade_snapshots(['2330'])
    print(snapshots[0])

    # list client's account holding positions
    pos = get_stock_positions()
    print(pos)

