#!/bin/bash
set -e # exit the script when execution hits any error

# Deploys one of the market symbol quotes Cloud Functions (gen2, HTTP trigger, Python 3.13) from this folder.
# See README.md for secret formats, response formats and troubleshooting.
#
# 1. get-tw-ticker-quotes: Taiwan stock snapshots from the SinoTrade Shioaji API (sinotrade.py).
# 2. get-us-ticker-quotes: US stock quotes from Alpaca stock snapshots
#    GET https://data.alpaca.markets/v2/stocks/snapshots (alpaca-quotes.py).
#
# [mandatory arguments]
#   --function FUNCTION              Function to deploy: get-tw-ticker-quotes or get-us-ticker-quotes.
#   --project PROJECT_ID             GCP project to deploy to, e.g. my-gcp-project.
#   --region REGION                  Region to deploy to, e.g. us-central1.
#
# [optional arguments]
#   --configuration NAME             gcloud configuration to deploy with, a NAME from
#                                    `gcloud config configurations list`. Its account is used; --project overrides its
#                                    project. Default: the active configuration.
#   --source DIR                     Folder with main.py and requirements.txt to deploy. Default: the folder of this
#                                    script, so the script can run from any working directory.
#
# [mandatory variables]
#   TW_NATIONAL_ID                   Key in the "sinotrade-api-key" secret that holds the SinoTrade api_key/api_key_secret.
#                                    Only for get-tw-ticker-quotes.
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
#   TW_NATIONAL_ID=... ./deploy.sh --function get-tw-ticker-quotes --project my-gcp-project --region us-central1
#   ./deploy.sh --function get-us-ticker-quotes --project my-gcp-project --region us-central1
#   ./deploy.sh --function get-us-ticker-quotes --project my-gcp-project --region us-central1 --configuration default
#   ./deploy.sh --function get-us-ticker-quotes --project my-gcp-project --region us-central1 --source ~/market_symbol_quotes
#
# All functions are deployed with --no-allow-unauthenticated; invoke them with a GCP identity token:
#   curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
#     "https://$REGION-$PROJECT_ID.cloudfunctions.net/get-tw-ticker-quotes?symbols=2330,00662,006208"
#   curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
#     "https://$REGION-$PROJECT_ID.cloudfunctions.net/get-us-ticker-quotes?tickers=VOO,QQQ"
# US symbols Alpaca cannot quote are listed in the X-Alpaca-Errors response header.

print_help() {
  cat <<EOF
Usage: $0 --function FUNCTION --project PROJECT_ID --region REGION [--configuration NAME] [--source DIR]

Deploys one market symbol quotes Cloud Function.

Options:
  --function FUNCTION   Function to deploy: get-tw-ticker-quotes (needs
                        \$TW_NATIONAL_ID) or get-us-ticker-quotes.
  --project PROJECT_ID  GCP project to deploy to, e.g. my-gcp-project.
  --region REGION       Region to deploy to, e.g. us-central1.
  --configuration NAME  Optional gcloud configuration to deploy with, from
                        \`gcloud config configurations list\`. Default: the
                        active configuration.
  --source DIR          Optional folder with main.py to deploy. Default: the
                        folder of this script ($SCRIPT_DIR).
  -h, --help            Show this help message and exit.
EOF
}

# Folder of this script, the default --source; resolved before parsing so print_help can show it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse command line arguments
FUNCTION=""
PROJECT_ID=""
REGION=""
GCLOUD_CONFIG=""
SOURCE_DIR="$SCRIPT_DIR"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --function || "$1" == --project || "$1" == --region || "$1" == --configuration || "$1" == --source ]] && [[ $# -lt 2 ]]; then
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
    --source)
      SOURCE_DIR="$2"
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
if [ "$FUNCTION" != "get-tw-ticker-quotes" ] && [ "$FUNCTION" != "get-us-ticker-quotes" ]; then
  echo "Error: --function must be get-tw-ticker-quotes or get-us-ticker-quotes."
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

if [ ! -f "$SOURCE_DIR/main.py" ]; then
  echo "Error: --source $SOURCE_DIR has no main.py; pass the market_symbol_quotes folder."
  print_help
  exit 1
fi

# Validate mandatory variables

if [ "$FUNCTION" = "get-tw-ticker-quotes" ] && [ -z "$TW_NATIONAL_ID" ]; then
  echo "Error: TW_NATIONAL_ID environment variable is not set; get-tw-ticker-quotes needs it."
  exit 1
fi

ALPACA_SECRET_NAME="${ALPACA_SECRET_NAME:-alpaca-api-key}"

# Runtime identity of all functions; reads the SinoTrade and Alpaca secrets from Secret Manager.
GCP_SA="smart-invest@$PROJECT_ID.iam.gserviceaccount.com"

set -x # print the executing lines

if [ "$FUNCTION" = "get-tw-ticker-quotes" ]; then
  # Taiwan quotes: SinoTrade API key is read from the "sinotrade-api-key" secret using $TW_NATIONAL_ID.
  gcloud functions deploy get-tw-ticker-quotes \
    --gen2 --region=$REGION \
    --runtime=python313 \
    --trigger-http \
    --timeout=100 \
    --source="$SOURCE_DIR" \
    --entry-point=get_tw_ticker_quotes \
    --quiet \
    --service-account=$GCP_SA \
    --no-allow-unauthenticated --project $PROJECT_ID ${GCLOUD_CONFIG:+--configuration=$GCLOUD_CONFIG} \
    --set-env-vars TW_NATIONAL_ID=$TW_NATIONAL_ID \
    --memory=1024MiB
fi

if [ "$FUNCTION" = "get-us-ticker-quotes" ]; then
  # US quotes from Alpaca: the API key is read from the $ALPACA_SECRET_NAME secret.
  gcloud functions deploy get-us-ticker-quotes \
    --gen2 --region=$REGION \
    --runtime=python313 \
    --trigger-http \
    --timeout=100 \
    --source="$SOURCE_DIR" \
    --entry-point=get_us_ticker_quotes \
    --quiet \
    --service-account=$GCP_SA \
    --no-allow-unauthenticated --project $PROJECT_ID ${GCLOUD_CONFIG:+--configuration=$GCLOUD_CONFIG} \
    --set-env-vars "ALPACA_SECRET_NAME=$ALPACA_SECRET_NAME${ALPACA_DATA_FEED:+,ALPACA_DATA_FEED=$ALPACA_DATA_FEED}" \
    --memory=512MiB
fi
