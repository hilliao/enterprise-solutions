#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

# Deploys the market symbol quotes Cloud Functions (gen2, HTTP trigger, Python 3.13) from this folder.
# See README.md for secret formats, response formats and troubleshooting.
#
# 1. get_tw_stock_quotes: Taiwan stock snapshots from the SinoTrade Shioaji API (sinotrade.py).
# 2. get_us_stock_quotes: US stock quotes from the TradeStation quote snapshot API
#    GET https://api.tradestation.com/v3/marketdata/quotes/{symbols} (tradestation.py).
#
# [mandatory variables]
#   PROJECT_ID                       GCP project to deploy to, e.g. hil-financial-services.
#   TW_NATIONAL_ID                   Key in the "sinotrade-api-key" secret that holds the SinoTrade api_key/api_key_secret.
#   TRADE_STATION_OAUTH_SECRET_NAME  Secret Manager secret with TradeStation client_id/client_secret/refresh_token
#                                    per account, e.g. TradeStation_OAuth0.
#
# [prerequisites]
#   - Service account smart-invest@$PROJECT_ID.iam.gserviceaccount.com exists and has
#     roles/secretmanager.secretAccessor on the secrets above.
#   - The deployer has roles/cloudfunctions.developer and roles/iam.serviceAccountUser on that service account.
#
# [usage]
#   PROJECT_ID=hil-financial-services TW_NATIONAL_ID=... TRADE_STATION_OAUTH_SECRET_NAME=TradeStation_OAuth0 ./deploy.sh
#
# Both functions are deployed with --no-allow-unauthenticated; invoke them with a GCP identity token:
#   curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
#     "https://us-central1-$PROJECT_ID.cloudfunctions.net/get_tw_stock_quotes?symbols=2330,00662,006208"
#   curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
#     "https://us-central1-$PROJECT_ID.cloudfunctions.net/get_us_stock_quotes?tickers=VOO,QQQ"
# US symbols TradeStation cannot quote are listed in the X-TradeStation-Errors response header.

# Validate mandatory variables
if [ -z "$PROJECT_ID" ]; then
  echo "Error: PROJECT_ID environment variable is not set."
  exit 1
fi

if [ -z "$TW_NATIONAL_ID" ]; then
  echo "Error: TW_NATIONAL_ID environment variable is not set."
  exit 1
fi

if [ -z "$TRADE_STATION_OAUTH_SECRET_NAME" ]; then
  echo "Error: TRADE_STATION_OAUTH_SECRET_NAME environment variable is not set."
  exit 1
fi

# Runtime identity of both functions; reads the SinoTrade and TradeStation secrets from Secret Manager.
GCP_SA="smart-invest@$PROJECT_ID.iam.gserviceaccount.com"
REGION=us-central1

# Taiwan quotes: SinoTrade API key is read from the "sinotrade-api-key" secret using $TW_NATIONAL_ID.
gcloud functions deploy get-tw-stock-quotes \
  --gen2 --region=$REGION \
  --runtime=python313 \
  --trigger-http \
  --timeout=100 \
  --source=. \
  --entry-point=get_tw_stock_quotes \
  --quiet \
  --service-account=$GCP_SA \
  --no-allow-unauthenticated --project $PROJECT_ID \
  --set-env-vars TW_NATIONAL_ID=$TW_NATIONAL_ID \
  --memory=1024MiB \

# US quotes: TradeStation access tokens are refreshed from the refresh token in $TRADE_STATION_OAUTH_SECRET_NAME.
gcloud functions deploy get-us-stock-quotes \
  --gen2 --region=$REGION \
  --runtime=python313 \
  --trigger-http \
  --timeout=100 \
  --source=. \
  --entry-point=get_us_stock_quotes \
  --quiet \
  --service-account=$GCP_SA \
  --no-allow-unauthenticated --project $PROJECT_ID \
  --set-env-vars TRADE_STATION_OAUTH_SECRET_NAME=$TRADE_STATION_OAUTH_SECRET_NAME \
  --memory=512MiB \
