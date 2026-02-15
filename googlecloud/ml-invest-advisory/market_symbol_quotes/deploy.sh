#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

# This script deploys the Cloud Functions for market symbol quotes.
# It checks for required environment variables and deploys 2 Cloud functions:
# 1. get_tw_stock_quotes: Retrieves Taiwan stock quotes.
# 2. get_us_stock_quotes: Retrieves US stock quotes.

# [mandatory variables]
if [ -z "$PROJECT_ID" ]; then
  # Example of how to invoke with GCP identity token:
  # curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://us-central1-$PROJECT_ID.cloudfunctions.net/get_tw_stock_quotes?symbols=2330,00662,006208

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

GCP_SA="smart-invest@$PROJECT_ID.iam.gserviceaccount.com"
REGION=us-central1


gcloud functions deploy get_tw_stock_quotes \
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


gcloud functions deploy get_us_stock_quotes \
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
