import tempfile
import os

import shioaji as sj
import yaml
from google.cloud import secretmanager


def _access_secret(secret_id: str):
    """Helper function to access a secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    secret_version_name = client.secret_path(os.environ["PROJECT_ID"], secret_id) + "/versions/latest"
    request = {"name": secret_version_name}
    response = client.access_secret_version(request)
    return response.payload


def get_sinotrade_api_key(secret_id: str = "sinotrade-api-key"):
    """
    Accesses a secret's payload from Google Cloud Secret Manager.
    """
    payload = _access_secret(secret_id)
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
    payload = _access_secret(secret_id)
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


def get_sinotrade_snapshots(stock_symbols: list = ['2330', '006208', '00662']):
    global _cached_sinotrade_api_key_yaml, _cached_temp_pfx_path, _cached_temp_file_obj

    if _cached_sinotrade_api_key_yaml is None:
        _cached_sinotrade_api_key_yaml = get_sinotrade_api_key()
        print("Successfully cached SinoTrade API key from Secret Manager.")
    else:
        print("Using cached SinoTrade API key.")

    if _cached_temp_pfx_path is None:
        _cached_temp_pfx_path, _cached_temp_file_obj = get_sinotrade_ca_pfx()
        print(f"Successfully cached Sinotrade CA PFX file from Secret Manager. Path: {_cached_temp_pfx_path}")
    else:
        print(f"Using cached Sinotrade CA PFX file. Path: {_cached_temp_pfx_path}")

    api = sj.Shioaji()
    tw_national_id = os.environ['TW_NATIONAL_ID']
    accounts = api.login(_cached_sinotrade_api_key_yaml[tw_national_id]['api_key'],
                         _cached_sinotrade_api_key_yaml[tw_national_id]['api_key_secret'])
    api.activate_ca(ca_path=_cached_temp_pfx_path, ca_passwd=tw_national_id,
                    person_id=tw_national_id)
    contracts = [api.Contracts.Stocks[symbol] for symbol in stock_symbols]
    snapshots = api.snapshots(contracts)
    return snapshots


if __name__ == "__main__":
    snapshots = get_sinotrade_snapshots()
    for element in snapshots:
        print(f"{element['exchange']}.{element['code']} "
              f"has current buy price at "
              f"{element['buy_price']}")

    snapshots = get_sinotrade_snapshots(['2330'])