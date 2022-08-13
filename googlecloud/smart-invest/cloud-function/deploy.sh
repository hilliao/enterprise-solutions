FUNCTION_DIR=/home/hil/git/enterprise-solutions/googlecloud/smart-invest/cloud-function
PROJECT_ID=[***REQUIRED***]

SA="smart-invest@$PROJECT_ID.iam.gserviceaccount.com"
REGION=us-west1

gcloud beta functions deploy stock-quotes \
  --gen2 --region $REGION \
  --runtime python39 \
  --trigger-http \
  --entry-point stock_quotes \
  --source $FUNCTION_DIR \
  --service-account=$SA \
  --set-env-vars SECRET_MANAGER_PROJECT_ID=$PROJECT_ID,SECRET_NAME_YH_API_KEY=X-RapidAPI-Key,BUCKET=$PROJECT_ID-smart-invest \
  --set-env-vars SECRET_NAME_REFRESH_TOKEN=TradeStation_RefreshToken,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret \
  --set-env-vars FOLDER=quotes,PROJECT_ID=$PROJECT_ID --quiet --project $PROJECT_ID &

gcloud beta functions deploy execute-trade \
  --gen2 --region $REGION \
  --runtime python39 \
  --trigger-http --quiet \
  --entry-point execute_trade \
  --source $FUNCTION_DIR \
  --service-account=$SA \
  --set-env-vars BUCKET=$PROJECT_ID-smart-invest,FOLDER=quotes,PROJECT_ID=$PROJECT_ID,SECRET_MANAGER_PROJECT_ID=$PROJECT_ID \
  --set-env-vars SECRET_NAME_REFRESH_TOKEN=TradeStation_RefreshToken,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret \
  --project $PROJECT_ID &

gcloud beta functions deploy get-authorization-code \
  --gen2 --region $REGION --runtime python39 --trigger-http \
  --entry-point get_authorization_code --source $FUNCTION_DIR \
  --service-account=$SA --quiet --allow-unauthenticated \
  --set-env-vars SECRET_MANAGER_PROJECT_ID=$PROJECT_ID,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret,PROJECT_ID=$PROJECT_ID \
  --project $PROJECT_ID &
