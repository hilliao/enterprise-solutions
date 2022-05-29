FUNCTION_DIR=/home/hil/git/enterprise-solutions/googlecloud/smart-invest/cloud-function
PROJECT_ID=$(gcloud config get-value project)
SA=stockquote@test-vpc-341000.iam.gserviceaccount.com

gcloud beta functions deploy stock-quotes \
--gen2 --region us-west1 \
--runtime python39 \
--trigger-http \
--entry-point stock_quotes \
--source $FUNCTION_DIR \
--allow-unauthenticated \
--service-account=$SA \
--set-env-vars SECRET_MANAGER_PROJECT_ID=test-vpc-341000,SECRET_NAME_YH_API_KEY=X-RapidAPI-Key,BUCKET=test-vpc-341000 \
--set-env-vars SECRET_NAME_REFRESH_TOKEN=TradeStation_RefreshToken,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret \
--set-env-vars FOLDER=quotes,PROJECT_ID=$PROJECT_ID &

gcloud beta functions deploy trade-recommendation \
--gen2 --region us-west1 \
--runtime python39 \
--trigger-http \
--entry-point trade_recommendation \
--source $FUNCTION_DIR \
--allow-unauthenticated \
--service-account=$SA \
--set-env-vars BUCKET=test-vpc-341000,FOLDER=quotes,PROJECT_ID=$PROJECT_ID,SECRET_MANAGER_PROJECT_ID=test-vpc-341000 \
--set-env-vars SECRET_NAME_REFRESH_TOKEN=TradeStation_RefreshToken,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret &

gcloud beta functions deploy get-authorization-code \
 --gen2 --region us-west1 --runtime python39 --trigger-http \
 --entry-point get_authorization_code --source $FUNCTION_DIR \
 --allow-unauthenticated --service-account=$SA \
 --set-env-vars SECRET_MANAGER_PROJECT_ID=test-vpc-341000,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret,PROJECT_ID=$PROJECT_ID &
