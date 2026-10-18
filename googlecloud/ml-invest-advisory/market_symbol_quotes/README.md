# Market Symbol Quotes

Three HTTP Cloud Functions (gen2, running on Cloud Run) that return real-time stock quotes:

| Function | Market | Broker API | Source |
| :--- | :--- | :--- | :--- |
| `get_us_stock_quotes` | US | [TradeStation quote snapshots](https://api.tradestation.com/docs/specification#tag/MarketData/operation/GetQuoteSnapshots) `GET /v3/marketdata/quotes/{symbols}` | [tradestation.py](tradestation.py) |
| `get_us_ticker_quotes` | US | [Alpaca stock snapshots](https://alpaca.markets/sdks/python/market_data.html) `GET /v2/stocks/snapshots` | [alpaca-quotes.py](alpaca-quotes.py) |
| `get_tw_stock_quotes` | Taiwan | [SinoTrade Shioaji](https://sinotrade.github.io/) `api.snapshots()` | [sinotrade.py](sinotrade.py) |

All entry points are in [main.py](main.py). The US quotes are used by the portfolio reports in
[portfolio_reports](../portfolio_reports) (`STOCK_QUOTES_CLOUD_RUN_URL`, see [build_portfolio_prompt.py](../portfolio_reports/build_portfolio_prompt.py)).
The two US functions take the same parameters and return the same response format, so either URL can be used as
`STOCK_QUOTES_CLOUD_RUN_URL`.

## Files

| File | Purpose |
| :--- | :--- |
| [main.py](main.py) | HTTP entry points; validates the query parameters and maps errors to HTTP responses. |
| [tradestation.py](tradestation.py) | TradeStation OAuth refresh-token flow and quote snapshot request. |
| [alpaca-quotes.py](alpaca-quotes.py) | Alpaca stock snapshots converted to TradeStation's quote fields. Loaded with `importlib` because of the hyphen in its name. |
| [sinotrade.py](sinotrade.py) | SinoTrade login and snapshots; also `get_stock_positions()` for account holdings. |
| [gcp_data_access.py](gcp_data_access.py) | Reads the latest version of a Secret Manager secret. |
| [deploy.sh](deploy.sh) | Deploys all functions. |
| [requirements.txt](requirements.txt) | Python dependencies installed by Cloud Build at deploy time. |

## Secrets

Secrets are read from Secret Manager in `$PROJECT_ID`. On Cloud Run the project ID is read from the metadata server;
when running locally, set `PROJECT_ID` yourself.

**TradeStation** (`$TRADE_STATION_OAUTH_SECRET_NAME`, default `TradeStation_OAuth0`): JSON keyed by account.
Only the first account is used to request quotes.

```json
{
  "account_number_0": {
    "client_id": "...",
    "client_secret": "...",
    "refresh_token": "..."
  }
}
```

The refresh token must have been granted the `MarketData` scope. Access tokens are refreshed from it via
`https://signin.tradestation.com/oauth/token` and cached in memory per instance until 2 minutes before the
`expires_in` in the token response (20 minutes). If the quotes request returns `401` or `403`, tokens older than
5 minutes are refreshed and the request is retried once. See the comment at the top of
[tradestation.py](tradestation.py) for details.

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

## Deploy

```sh
export PROJECT_ID=hil-financial-services
export TW_NATIONAL_ID=...
export TRADE_STATION_OAUTH_SECRET_NAME=TradeStation_OAuth0
export ALPACA_SECRET_NAME=alpaca-api-key  # optional, this is the default
export ALPACA_DATA_FEED=sip  # optional, see "Alpaca data feed" below
./deploy.sh
```

The functions run as `smart-invest@$PROJECT_ID.iam.gserviceaccount.com`, which needs
`roles/secretmanager.secretAccessor` on the secrets above. All functions are deployed with
`--no-allow-unauthenticated`, so callers need `roles/run.invoker` and an identity token.

## Usage

### US quotes

`tickers` (or `symbols`) is a comma-separated list of US symbols.

```sh
curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://us-central1-$PROJECT_ID.cloudfunctions.net/get_us_stock_quotes?tickers=VOO,QQQ,MSFT"
```

Success returns `200` with the TradeStation quotes keyed by symbol:

```json
{
  "MSFT": {"Symbol": "MSFT", "Last": "509.355", "PreviousClose": "516.16998", "NetChangePct": "-1.32", "...": "..."},
  "VOO": {"Symbol": "VOO", "...": "..."}
}
```

Symbols TradeStation could not quote are left out of the body and listed in the `X-TradeStation-Errors`
response header, e.g. `[{"Symbol": "XYZ", "Error": "..."}]`. The body shape is kept as `{symbol: quote}`
because the portfolio report scripts treat every top-level key as a ticker.

### US quotes from Alpaca

`get_us_ticker_quotes` takes the same `tickers` (or `symbols`) parameter and returns the same `{symbol: quote}` body
with TradeStation's field names, computed from Alpaca's snapshot:

```sh
curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://us-central1-$PROJECT_ID.cloudfunctions.net/get-us-ticker-quotes?tickers=VOO,QQQ,MSFT"
```

```json
{
  "MSFT": {"Symbol": "MSFT", "Last": 509.355, "PreviousClose": 516.17, "NetChange": -6.815, "NetChangePct": -1.32, "...": "..."}
}
```

| Field | Alpaca source |
| :--- | :--- |
| `Last`, `LastSize`, `LastVenue`, `TradeTime` | `latest_trade` |
| `PreviousClose`, `PreviousVolume` | close and volume of the trading day before the latest trade |
| `NetChange`, `NetChangePct` | `Last - PreviousClose`; the percentage is in percent, like TradeStation's |
| `Open`, `High`, `Low`, `Close`, `Volume`, `VWAP` | `daily_bar`; left out in pre-market, before the day has a daily bar |
| `Bid`, `BidSize`, `Ask`, `AskSize` | `latest_quote` |

Differences from the TradeStation function:

- Prices are JSON numbers instead of strings; [build_portfolio_prompt.py](../portfolio_reports/build_portfolio_prompt.py) converts
  both with `float()`.
- Ticker symbols are upper-cased.
- Symbols Alpaca returns no snapshot for (unknown symbols), or that have no last trade or previous close, are left
  out of the body and listed in the `X-Alpaca-Errors` response header, e.g. `[{"Symbol": "XYZ", "Error": "..."}]`.

**Alpaca data feed**: without `ALPACA_DATA_FEED`, Alpaca uses SIP (all US exchanges) if the account has a paid market
data subscription, and IEX otherwise. IEX is a single exchange, so `Last` can lag the consolidated price for thinly
traded symbols. Set `ALPACA_DATA_FEED` (`sip`, `iex`, `delayed_sip`, ...) at deploy time to choose a feed;
requesting `sip` without a subscription makes Alpaca return an error.

### Taiwan quotes

`symbols` is a comma-separated list of TWSE/TPEx codes. The response is a JSON list of Shioaji snapshots.

```sh
curl -sS -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://us-central1-$PROJECT_ID.cloudfunctions.net/get_tw_stock_quotes?symbols=2330,00662,006208"
```

### Errors

| Status | Cause |
| :--- | :--- |
| `400` | Missing or empty `symbols` / `tickers`. |
| `405` | Request method is not `GET`. |
| `500` | TradeStation, Alpaca or SinoTrade call failed. |

When TradeStation returns a non-200 response, the `500` body includes TradeStation's error body as `detail`:

```json
{
  "error": "TradeStation API returned 403 for url: https://api.tradestation.com/v3/marketdata/quotes/VOO",
  "detail": {"Error": "Forbidden", "Message": "..."}
}
```

When Alpaca returns a non-200 response, the `500` body is
`{"error": "Alpaca API returned 403", "detail": "<Alpaca's response body>"}`. alpaca-py retries `429` and `504`
3 times, 3 seconds apart, before giving up.

## Logging

[tradestation.py](tradestation.py), [alpaca-quotes.py](alpaca-quotes.py) and the US entry points log JSON lines (`{"severity": ..., "message": ...}`),
which Cloud Logging records at the given severity. TradeStation and Alpaca error responses and unexpected exceptions
(with traceback) are logged at `ERROR`; per-symbol errors at `WARNING`.

```sh
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="get-us-stock-quotes" AND severity>=WARNING' \
  --project $PROJECT_ID --limit 20 --freshness 1d
```

## Run locally

```sh
pip install -r requirements.txt
gcloud auth application-default login
export PROJECT_ID=hil-financial-services TRADE_STATION_OAUTH_SECRET_NAME=TradeStation_OAuth0
functions-framework --target=get_us_stock_quotes --port=8080
curl -sS "http://localhost:8080/?tickers=VOO,QQQ"
```

For Alpaca, use `--target=get_us_ticker_quotes`; it only needs `PROJECT_ID`.

## Troubleshooting

**TradeStation `403 Forbidden`**: check the `detail` field or the `ERROR` log for TradeStation's message. The log
also shows `access token issued Ns ago`; a token only seconds or minutes old, especially right after a
`retrying with a refreshed access token` warning, means the token isn't the cause. Then reproduce outside Cloud Run
with the same refresh token:

```sh
CREDS=$(gcloud secrets versions access latest --secret="$TRADE_STATION_OAUTH_SECRET_NAME" --project="$PROJECT_ID" \
  | jq -c 'to_entries[0].value')
TS_TOKEN=$(curl -sS -X POST "https://signin.tradestation.com/oauth/token" \
  -H "content-type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=refresh_token" \
  --data-urlencode "client_id=$(jq -r .client_id <<<"$CREDS")" \
  --data-urlencode "client_secret=$(jq -r .client_secret <<<"$CREDS")" \
  --data-urlencode "refresh_token=$(jq -r .refresh_token <<<"$CREDS")" | jq -r .access_token)
curl -sS -i -H "Authorization: Bearer $TS_TOKEN" "https://api.tradestation.com/v3/marketdata/quotes/VOO,QQQ"
```

- Fails locally too: the refresh token is missing the `MarketData` scope, or the account's market data
  agreement needs to be signed or renewed.
- Works locally but fails from Cloud Run: TradeStation is likely rejecting Cloud Run's egress IPs; route egress
  through a static IP (Serverless VPC Access connector + Cloud NAT).

The streaming endpoint `/v3/marketdata/stream/quotes/{symbols}` started returning `403` from Cloud Run in
September 2026 while the snapshot endpoint kept working, which is why the function uses snapshots.
