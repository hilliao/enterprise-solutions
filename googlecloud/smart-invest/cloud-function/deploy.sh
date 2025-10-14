#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

# [mandatory variables]
FUNCTION_DIR=/home/hil/git/enterprise-solutions/googlecloud/smart-invest/cloud-function
PROJECT_ID=[***REQUIRED***]
SECRET_NAME=TradeStation_OAuth0
SA="smart-invest@$PROJECT_ID.iam.gserviceaccount.com"
REGION=us-central1

gcloud functions deploy stock-quotes \
  --gen2 --region=$REGION \
  --runtime=python313 \
  --trigger-http \
  --timeout=100 \
  --entry-point=stock_quotes \
  --source=$FUNCTION_DIR \
  --service-account=$SA \
  --set-env-vars SECRET_MANAGER_PROJECT_ID=$PROJECT_ID,SECRET_NAME_YH_API_KEY=X-RapidAPI-Key,BUCKET=$PROJECT_ID-smart-invest \
  --set-env-vars SECRET_NAME_TradeStation_OAuth0=$SECRET_NAME \
  --set-env-vars FOLDER=quotes,PROJECT_ID=$PROJECT_ID \
  --quiet \
  --no-allow-unauthenticated --project $PROJECT_ID &

gcloud functions deploy execute-trade \
  --gen2 --region $REGION \
  --runtime python312 \
  --trigger-http --quiet \
  --entry-point execute_trade \
  --source $FUNCTION_DIR \
  --service-account=$SA \
  --set-env-vars BUCKET=$PROJECT_ID-smart-invest,FOLDER=quotes,PROJECT_ID=$PROJECT_ID,SECRET_MANAGER_PROJECT_ID=$PROJECT_ID \
  --set-env-vars SECRET_NAME_TradeStation_OAuth0=$SECRET_NAME \
  --project $PROJECT_ID &

gcloud beta functions deploy get-authorization-code \
  --gen2 --region $REGION --runtime python312 --trigger-http \
  --entry-point get_authorization_code --source $FUNCTION_DIR \
  --service-account=$SA --quiet --allow-unauthenticated \
  --set-env-vars SECRET_MANAGER_PROJECT_ID=$PROJECT_ID,SECRET_NAME_TradeStation_OAuth0=$SECRET_NAME,PROJECT_ID=$PROJECT_ID \
  --project $PROJECT_ID &
