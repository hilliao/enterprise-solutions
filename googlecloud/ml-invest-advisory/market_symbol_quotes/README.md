# Market Symbol Quotes

Two HTTP Cloud Functions (gen2, running on Cloud Run) that return real-time stock quotes:

| Function | Market | Broker API | Source |
| :--- | :--- | :--- | :--- |
| `get_us_stock_quotes` | US | [TradeStation quote snapshots](https://api.tradestation.com/docs/specification#tag/MarketData/operation/GetQuoteSnapshots) `GET /v3/marketdata/quotes/{symbols}` | [tradestation.py](tradestation.py) |
| `get_tw_stock_quotes` | Taiwan | [SinoTrade Shioaji](https://sinotrade.github.io/) `api.snapshots()` | [sinotrade.py](sinotrade.py) |

Both entry points are in [main.py](main.py). The US quotes are used by the portfolio reports in
[local_llm](../local_llm) (`STOCK_QUOTES_CLOUD_RUN_URL`, see [generate-llm-prompt.py](../local_llm/generate-llm-prompt.py)).

## Files

| File | Purpose |
| :--- | :--- |
| [main.py](main.py) | HTTP entry points; validates the query parameters and maps errors to HTTP responses. |
| [tradestation.py](tradestation.py) | TradeStation OAuth refresh-token flow and quote snapshot request. |
| [sinotrade.py](sinotrade.py) | SinoTrade login and snapshots; also `get_stock_positions()` for account holdings. |
| [gcp_data_access.py](gcp_data_access.py) | Reads the latest version of a Secret Manager secret. |
| [deploy.sh](deploy.sh) | Deploys both functions. |
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
./deploy.sh
```

The functions run as `smart-invest@$PROJECT_ID.iam.gserviceaccount.com`, which needs
`roles/secretmanager.secretAccessor` on the secrets above. Both functions are deployed with
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
| `500` | TradeStation or SinoTrade call failed. |

When TradeStation returns a non-200 response, the `500` body includes TradeStation's error body as `detail`:

```json
{
  "error": "TradeStation API returned 403 for url: https://api.tradestation.com/v3/marketdata/quotes/VOO",
  "detail": {"Error": "Forbidden", "Message": "..."}
}
```

## Logging

[tradestation.py](tradestation.py) and `get_us_stock_quotes` log JSON lines (`{"severity": ..., "message": ...}`),
which Cloud Logging records at the given severity. TradeStation error responses and unexpected exceptions
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
