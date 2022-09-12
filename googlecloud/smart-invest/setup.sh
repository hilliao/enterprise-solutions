#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

# [mandatory variables]
PROJECT_ID=[***REQUIRED***]
REGION=us-west1

# Enable secret manager API
gcloud services enable secretmanager.googleapis.com  --project $PROJECT_ID

# Create service accounts and grant IAM roles
gcloud iam service-accounts create smart-invest \
    --description="Run cloud function" \
    --display-name="BigQuery Admin, Cloud Debugger Agent, Cloud Trace Agent, Logs Writer, Storage Admin" --project $PROJECT_ID

for role in roles/bigquery.admin roles/clouddebugger.agent roles/cloudtrace.agent roles/logging.logWriter roles/storage.admin
do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:smart-invest@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="$role" --project $PROJECT_ID
done
gcloud iam service-accounts create smart-invest-func-invoker \
    --description="Call cloud functions" \
    --display-name="Grant cloud function invoker role to functions, cloud run invoker to function's cloud run service" \
    --project $PROJECT_ID

# create secrets. after secrets are created, manually add versions to each secret
for secret_name in X-RapidAPI-Key TradeStation_RefreshToken TradeStation_Client_ID_Secret
do
  gcloud secrets create $secret_name \
    --replication-policy=user-managed --locations=$REGION --project $PROJECT_ID
  gcloud secrets add-iam-policy-binding $secret_name \
    --member="serviceAccount:smart-invest@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"  --project $PROJECT_ID
done

# Create a storage bucket for storing cached quotes
BUCKET=$PROJECT_ID-smart-invest
gcloud alpha storage buckets create gs://$BUCKET --location=$REGION --project $PROJECT_ID

# Enable cloud function related APIs for deploying code
gcloud services enable cloudfunctions.googleapis.com  --project $PROJECT_ID
gcloud services enable run.googleapis.com  --project $PROJECT_ID
gcloud services enable artifactregistry.googleapis.com --project $PROJECT_ID
gcloud services enable cloudbuild.googleapis.com --project $PROJECT_ID
gcloud services enable cloudscheduler.googleapis.com --project $PROJECT_ID

# Create Cloud Scheduler job
FUNC_URL=https://stock-quotes-[***REQUIRED_URL***]-uw.a.run.app
gcloud scheduler jobs create http after-market-stock-quotes --schedule="0 15 * * 1-5" --location $REGION \
--uri="$FUNC_URL/?tickers=QQQ,ONEQ,IVV,VOO,JETS,VHT,VDE,VFH,VTWO,BRK-B,ACN,AMD,GOOGL,AMZN,MSFT,MRVL,META,QCOM,CRM,SNAP,TSM,BHP,RIO,EXPE,BKNG,HD,NIO,NVDA,VTV" \
--http-method=POST --oidc-service-account-email=smart-invest-func-invoker@$PROJECT_ID.iam.gserviceaccount.com \
--time-zone="America/Los_Angeles" \
--description="get quotes from Yahoo Finance and save to cloud storage" \
--oidc-token-audience=$FUNC_URL --project $PROJECT_ID

# Grant cloud run and cloud function invoker IAM roles
gcloud functions add-iam-policy-binding stock-quotes --region=$REGION \
--member=serviceAccount:smart-invest-func-invoker@$PROJECT_ID.iam.gserviceaccount.com \
--gen2 --role=roles/cloudfunctions.invoker --project $PROJECT_ID
gcloud run services add-iam-policy-binding stock-quotes --region=$REGION \
--member=serviceAccount:smart-invest-func-invoker@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/run.invoker --project $PROJECT_ID
