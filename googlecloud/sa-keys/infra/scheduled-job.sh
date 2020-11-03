#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

PROJECT_ID="must enter"
RUN_URL=`partial cloud run url` # for https://$RUN_URL.a.run.app
GCP_SA_NAME=`service account name before @`
NAME=${PWD##*/}

gcloud scheduler jobs create http $NAME --schedule="0 0 * * *" --time-zone="America/New_York" \
  --message-body='{"secret-regex": "^hil"}'  --project $PROJECT_ID \
  --oidc-service-account-email=$GCP_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com --http-method=PUT \
  --oidc-token-audience="https://$RUN_URL.a.run.app" --uri=https://$RUN_URL.a.run.app/projects/$PROJECT_ID/audit-secrets \
  --headers Content-Type=application/json