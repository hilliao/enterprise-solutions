#!/bin/bash
set -e # exit the script when execution hits any error

# Deploys one of the market symbol quotes Cloud Functions (gen2, HTTP trigger, Python 3.13) from this folder.
# See README.md for secret formats, response formats and troubleshooting.
#
# 1. get-tw-stock-quotes: Taiwan stock snapshots from the SinoTrade Shioaji API (sinotrade.py).
# 2. get-us-ticker-quotes: US stock quotes from Alpaca stock snapshots
#    GET https://data.alpaca.markets/v2/stocks/snapshots (alpaca-quotes.py).
# OBSOLETE, no longer deployed: get_us_stock_quotes, US stock quotes from the retired TradeStation API
#    GET https://api.tradestation.com/v3/marketdata/quotes/{symbols} (tradestation_obsolete.py). Its gcloud command
#    below is commented out; the Alpaca function returns the same response format.
#
# [mandatory arguments]
#   --function FUNCTION              Function to deploy: get-tw-stock-quotes or get-us-ticker-quotes.
#   --project PROJECT_ID             GCP project to deploy to, e.g. my-gcp-project.
#   --region REGION                  Region to deploy to, e.g. us-central1.
#
# [optional arguments]
#   --configuration NAME             gcloud configuration to deploy with, a NAME from
#                                    `gcloud config configurations list`. Its account is used; --project overrides its
#                                    project. Default: the active configuration.
#
# [mandatory variables]
#   TW_NATIONAL_ID                   Key in the "sinotrade-api-key" secret that holds the SinoTrade api_key/api_key_secret.
#                                    Only for get-tw-stock-quotes.
#   (OBSOLETE: TRADE_STATION_OAUTH_SECRET_NAME was only needed by the retired TradeStation function.)
#
# [optional variables]
#   ALPACA_SECRET_NAME               Secret Manager secret with the Alpaca API key in YAML with "key" and "secret"
#                                    attributes. Default: alpaca-api-key. Only for get-us-ticker-quotes.
#   ALPACA_DATA_FEED                 Alpaca data feed, e.g. sip or iex. Default: Alpaca picks SIP with a paid
#                                    subscription, otherwise IEX. Only for get-us-ticker-quotes.
#
# [prerequisites]
#   - Service account smart-invest@$PROJECT_ID.iam.gserviceaccount.com exists and has
#     roles/secretmanager.secretAccessor on the secrets above, including $ALPACA_SECRET_NAME.
#   - The deployer has roles/cloudfunctions.developer and roles/iam.serviceAccountUser on that service account.
#
# [usage]
#   TW_NATIONAL_ID=... ./deploy.sh --function get-tw-stock-quotes --project my-gcp-project --region us-central1
#   ./deploy.sh --function get-us-ticker-quotes --project my-gcp-project --region us-central1
#   ./deploy.sh --function get-us-ticker-quotes --project my-gcp-project --region us-central1 --configuration default
#
# All functions are deployed with --no-allow-unauthenticated; invoke them with a GCP identity token:
#   curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
#     "https://$REGION-$PROJECT_ID.cloudfunctions.net/get-tw-stock-quotes?symbols=2330,00662,006208"
#   curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
#     "https://$REGION-$PROJECT_ID.cloudfunctions.net/get-us-ticker-quotes?tickers=VOO,QQQ"
# US symbols Alpaca cannot quote are listed in the X-Alpaca-Errors response header.

print_help() {
  cat <<EOF
Usage: $0 --function FUNCTION --project PROJECT_ID --region REGION [--configuration NAME]

Deploys one market symbol quotes Cloud Function.

Options:
  --function FUNCTION   Function to deploy: get-tw-stock-quotes (needs
                        \$TW_NATIONAL_ID) or get-us-ticker-quotes.
  --project PROJECT_ID  GCP project to deploy to, e.g. my-gcp-project.
  --region REGION       Region to deploy to, e.g. us-central1.
  --configuration NAME  Optional gcloud configuration to deploy with, from
                        \`gcloud config configurations list\`. Default: the
                        active configuration.
  -h, --help            Show this help message and exit.
EOF
}

# Parse command line arguments
FUNCTION=""
PROJECT_ID=""
REGION=""
GCLOUD_CONFIG=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --function || "$1" == --project || "$1" == --region || "$1" == --configuration ]] && [[ $# -lt 2 ]]; then
    echo "Error: $1 needs a value."
    print_help
    exit 1
  fi
  case $1 in
    --function)
      FUNCTION="$2"
      shift 2
      ;;
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --configuration)
      GCLOUD_CONFIG="$2"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      print_help
      exit 1
      ;;
  esac
done

# Validate mandatory arguments
if [ "$FUNCTION" != "get-tw-stock-quotes" ] && [ "$FUNCTION" != "get-us-ticker-quotes" ]; then
  echo "Error: --function must be get-tw-stock-quotes or get-us-ticker-quotes."
  print_help
  exit 1
fi

if [ -z "$PROJECT_ID" ]; then
  echo "Error: --project is not set."
  print_help
  exit 1
fi

if [ -z "$REGION" ]; then
  echo "Error: --region is not set."
  print_help
  exit 1
fi

# Validate mandatory variables

if [ "$FUNCTION" = "get-tw-stock-quotes" ] && [ -z "$TW_NATIONAL_ID" ]; then
  echo "Error: TW_NATIONAL_ID environment variable is not set; get-tw-stock-quotes needs it."
  exit 1
fi

# OBSOLETE: only the retired TradeStation function needed TRADE_STATION_OAUTH_SECRET_NAME.
# if [ -z "$TRADE_STATION_OAUTH_SECRET_NAME" ]; then
#   echo "Error: TRADE_STATION_OAUTH_SECRET_NAME environment variable is not set."
#   exit 1
# fi

ALPACA_SECRET_NAME="${ALPACA_SECRET_NAME:-alpaca-api-key}"

# Runtime identity of all functions; reads the SinoTrade and Alpaca secrets from Secret Manager.
GCP_SA="smart-invest@$PROJECT_ID.iam.gserviceaccount.com"

set -x # print the executing lines

if [ "$FUNCTION" = "get-tw-stock-quotes" ]; then
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
    --no-allow-unauthenticated --project $PROJECT_ID ${GCLOUD_CONFIG:+--configuration=$GCLOUD_CONFIG} \
    --set-env-vars TW_NATIONAL_ID=$TW_NATIONAL_ID \
    --memory=1024MiB
fi

# OBSOLETE: the TradeStation API is retired, so get-us-stock-quotes (tradestation_obsolete.py) is no longer deployed.
# US quotes: TradeStation access tokens are refreshed from the refresh token in $TRADE_STATION_OAUTH_SECRET_NAME.
# gcloud functions deploy get-us-stock-quotes \
#   --gen2 --region=$REGION \
#   --runtime=python313 \
#   --trigger-http \
#   --timeout=100 \
#   --source=. \
#   --entry-point=get_us_stock_quotes \
#   --quiet \
#   --service-account=$GCP_SA \
#   --no-allow-unauthenticated --project $PROJECT_ID \
#   --set-env-vars TRADE_STATION_OAUTH_SECRET_NAME=$TRADE_STATION_OAUTH_SECRET_NAME \
#   --memory=512MiB \

if [ "$FUNCTION" = "get-us-ticker-quotes" ]; then
  # US quotes from Alpaca: the API key is read from the $ALPACA_SECRET_NAME secret.
  gcloud functions deploy get-us-ticker-quotes \
    --gen2 --region=$REGION \
    --runtime=python313 \
    --trigger-http \
    --timeout=100 \
    --source=. \
    --entry-point=get_us_ticker_quotes \
    --quiet \
    --service-account=$GCP_SA \
    --no-allow-unauthenticated --project $PROJECT_ID ${GCLOUD_CONFIG:+--configuration=$GCLOUD_CONFIG} \
    --set-env-vars "ALPACA_SECRET_NAME=$ALPACA_SECRET_NAME${ALPACA_DATA_FEED:+,ALPACA_DATA_FEED=$ALPACA_DATA_FEED}" \
    --memory=512MiB
fi
