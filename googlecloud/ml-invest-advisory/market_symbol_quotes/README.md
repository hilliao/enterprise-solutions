# Market Symbol Quotes

Two HTTP Cloud Functions (gen2, running on Cloud Run) that return real-time stock quotes:

| Function | Market | Broker API | Source |
| :--- | :--- | :--- | :--- |
| `get_us_ticker_quotes` | US | [Alpaca stock snapshots](https://alpaca.markets/sdks/python/market_data.html) `GET /v2/stocks/snapshots` | [alpaca-quotes.py](alpaca-quotes.py) |
| `get_tw_ticker_quotes` | Taiwan | [SinoTrade Shioaji](https://sinotrade.github.io/) `api.snapshots()` | [sinotrade.py](sinotrade.py) |

All entry points are in [main.py](main.py). The US quotes (Alpaca) are used by the portfolio reports in
[portfolio_reports](../portfolio_reports) (`STOCK_QUOTES_CLOUD_RUN_URL`, see [build_portfolio_prompt.py](../portfolio_reports/build_portfolio_prompt.py)).
Use the `get-us-ticker-quotes` URL as `STOCK_QUOTES_CLOUD_RUN_URL`.

## Files

| File | Purpose |
| :--- | :--- |
| [main.py](main.py) | HTTP entry points; validates the query parameters and maps errors to HTTP responses. |
| [alpaca-quotes.py](alpaca-quotes.py) | Alpaca stock snapshots converted to quotes by `snapshot_to_quote()`. Loaded with `importlib` because of the hyphen in its name. |
| [sinotrade.py](sinotrade.py) | SinoTrade login and snapshots; also `get_stock_positions()` for account holdings. |
| [gcp_data_access.py](gcp_data_access.py) | Reads the latest version of a Secret Manager secret. |
| [test_alpaca_quotes.py](test_alpaca_quotes.py) | Unit tests for `snapshot_to_quote()` and `get_alpaca_realtime_quotes()`, with Alpaca mocked. |
| [test_main.py](test_main.py) | Unit tests for the HTTP entry points in `main.py`, with SinoTrade, Alpaca and the Metadata Server mocked. |
| [test_sinotrade.py](test_sinotrade.py) | Unit tests for `get_sinotrade_snapshots()`, plus a live test against the SinoTrade simulation server. |
| [structured_logging.py](structured_logging.py) | `log()` writes JSON lines with a severity for Cloud Logging. |
| [deploy.sh](deploy.sh) | Deploys the Alpaca or the SinoTrade function, one per run. |
| [.gcloudignore](.gcloudignore) | Leaves `shioaji.log` (it can contain the Taiwan national ID), tests, caches and deploy tooling out of the uploaded source. |
| [requirements.txt](requirements.txt) | Python dependencies installed by Cloud Build at deploy time. |

## Secrets

Secrets are read from Secret Manager in `$PROJECT_ID`. On Cloud Run the project ID is read from the metadata server;
when running locally, set `PROJECT_ID` yourself.

**Alpaca** (`$ALPACA_SECRET_NAME`, default `alpaca-api-key`): YAML with the API key ID and
secret key. The key is read once per instance; Alpaca API keys don't expire.

```yaml
key: AK...
secret: ...
```

**SinoTrade** (`sinotrade-api-key`): YAML keyed by the Taiwan national ID in `$TW_NATIONAL_ID`.

```yaml
A123456789:
  api_key: ...
  api_key_secret: ...
```

## Tests

Install the dependencies and pytest, then run the tests from this folder:

```sh
pip install -r requirements.txt pytest
python -m pytest -v
```

The live SinoTrade tests in `test_sinotrade.py` log in to the simulation server and are skipped unless `PROJECT_ID`
and `TW_NATIONAL_ID` are set and Application Default Credentials can read the `sinotrade-api-key` secret:

```sh
gcloud auth application-default login
export PROJECT_ID=my-gcp-project
export TW_NATIONAL_ID=...
python -m pytest -v -s test_sinotrade.py
```

## Deploy

`deploy.sh` deploys one function per run, chosen with the mandatory `--function`, `--project` and `--region`
arguments. Add `--configuration NAME` to deploy with a gcloud configuration from
`gcloud config configurations list` instead of the active one. The source folder defaults to the folder of
`deploy.sh`, so it can run from any working directory; pass `--source DIR` to deploy another copy of this folder.

```sh
# US quotes from Alpaca
export ALPACA_SECRET_NAME=alpaca-api-key  # optional, this is the default
export ALPACA_DATA_FEED=sip  # optional, see "Alpaca data feed" below
./deploy.sh --function get-us-ticker-quotes --project my-gcp-project --region us-central1

# Taiwan quotes from SinoTrade
export TW_NATIONAL_ID=...
./deploy.sh --function get-tw-ticker-quotes --project my-gcp-project --region us-central1
```

The functions run as `smart-invest@<--project>.iam.gserviceaccount.com`, which needs
`roles/secretmanager.secretAccessor` on the secrets above. All functions are deployed with
`--no-allow-unauthenticated`, so callers need `roles/run.invoker` and an identity token.

## Usage

### US quotes from Alpaca

`get_us_ticker_quotes` takes a comma-separated `tickers` (or `symbols`) parameter and returns a `{symbol: quote}` body
computed from Alpaca's snapshot; ticker symbols are upper-cased. Prices and volumes are JSON numbers.

```sh
curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-us-ticker-quotes?tickers=VOO,XYZQ"
```

```
HTTP/2 200
x-alpaca-errors: [{"symbol": "XYZQ", "error": "Alpaca returned no snapshot for the symbol"}]
```

```json
{
  "VOO": {
    "symbol": "VOO", "price": 675.9, "previous-close": 673.94, "net-change": 1.96, "net-change-%": 0.29,
    "trade-time": "2026-11-06T21:00:03Z",
    "open": 675.435, "high": 681.44, "low": 675.34, "close": 676.02, "volume": 109275.0,
    "bid": 655.12, "ask": 696.49
  }
}
```

| Field | Meaning | Alpaca source |
| :--- | :--- | :--- |
| `symbol` | Ticker symbol, upper-cased | snapshot symbol |
| `price` | Latest trade price, including pre-market and after-hours trades | `latest_trade` |
| `previous-close` | Close of the trading day before the latest trade | `previous_daily_bar`, or `daily_bar` in pre-market |
| `net-change` | `price - previous-close`, rounded to 4 decimals | |
| `net-change-%` | `net-change` in percent of `previous-close`, rounded to 2 decimals: `0.29` means 0.29% | |
| `trade-time` | Latest trade time in UTC | `latest_trade` |
| `open`, `high`, `low`, `close`, `volume` | Regular session's daily bar; left out in pre-market, before the day has one | `daily_bar` |
| `bid`, `ask` | Latest bid and ask prices; left out when Alpaca has no quote | `latest_quote` |

Symbols Alpaca returns no snapshot for (unknown symbols), or that have no last trade or previous close, are left out
of the body and listed in the `X-Alpaca-Errors` response header.

**Alpaca data feed**: without `ALPACA_DATA_FEED`, Alpaca uses SIP (all US exchanges) if the account has a paid market
data subscription, and IEX otherwise. IEX is a single exchange, so `price` can lag the consolidated price for thinly
traded symbols. Set `ALPACA_DATA_FEED` (`sip`, `iex`, `delayed_sip`, ...) at deploy time to choose a feed;
requesting `sip` without a subscription makes Alpaca return an error.

### Taiwan quotes

`get_tw_ticker_quotes` takes a comma-separated `symbols` (or `tickers`) parameter of TWSE/TPEx codes and returns a
`{symbol: quote}` body with the same keys as the US quotes, plus `currency`; see `snapshot_to_quote()` in
[sinotrade.py](sinotrade.py). Prices are in TWD. The quotes come from SinoTrade's simulation server. Each request
logs in to SinoTrade and logs out when done, because SinoTrade allows only 5 logged-in connections per national ID.

```sh
curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-tw-ticker-quotes?symbols=2330,NOPE99"
```

```
HTTP/2 200
x-sinotrade-errors: [{"symbol": "NOPE99", "error": "SinoTrade has no contract for the symbol"}]
```

```json
{
  "2330": {
    "symbol": "2330", "price": 2135.0, "previous-close": 2240.0, "net-change": -105.0, "net-change-%": -4.68,
    "trade-time": "2026-11-06T06:30:00Z", "open": 2020.0, "high": 2195.0, "low": 2020.0,
    "bid": 2135.0, "ask": 2140.0, "currency": "TWD"
  }
}
```

| Field | Shioaji snapshot source |
| :--- | :--- |
| `price` | `close`, the latest trade price |
| `previous-close` | `close - change_price` |
| `net-change`, `net-change-%` | `change_price`, `change_rate` |
| `trade-time` | `ts`, Taiwan wall-clock time as nanoseconds since the epoch, converted to UTC; the sample's 06:30Z is 14:30 in Taipei, when the after-hours session ends |
| `open`, `high`, `low` | `open`, `high`, `low` |
| `bid`, `ask` | `buy_price`, `sell_price` |

Unlike the US quotes there is no `close`, which would equal `price`, and no `volume`, whose unit Shioaji doesn't
document. Unknown symbols are left out of the body and listed in the `X-SinoTrade-Errors` response header.

### Errors

| Status | Cause |
| :--- | :--- |
| `400` | Missing or empty `symbols` / `tickers`. |
| `405` | Request method is not `GET`. |
| `500` | Alpaca or SinoTrade call failed. |

When Alpaca returns a non-200 response, the `500` body is
`{"error": "Alpaca API returned 403", "detail": "<Alpaca's response body>"}`. alpaca-py retries `429` and `504`
3 times, 3 seconds apart, before giving up.

## Logging

[alpaca-quotes.py](alpaca-quotes.py), [sinotrade.py](sinotrade.py) and the entry points log JSON lines with `log()` from [structured_logging.py](structured_logging.py) (`{"severity": ..., "message": ...}`),
which Cloud Logging records at the given severity. Alpaca error responses and unexpected exceptions (with traceback)
are logged at `ERROR`; per-symbol errors at `WARNING`. A line with only `severity` and `message` is stored with the
message in `textPayload`.

```sh
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="get-us-ticker-quotes" AND severity>=WARNING' \
  --project $PROJECT_ID --limit 20 --freshness 1d
```

## Run locally

```sh
pip install -r requirements.txt
gcloud auth application-default login
export PROJECT_ID=my-gcp-project
functions-framework --target=get_us_ticker_quotes --port=8080
curl -sS "http://localhost:8080/?tickers=VOO,QQQ"
```

The Alpaca function only needs `PROJECT_ID`.
