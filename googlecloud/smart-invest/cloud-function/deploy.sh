FUNCTION_DIR=/home/hil/git/enterprise-solutions/googlecloud/smart-invest/cloud-function
PROJECT_ID=$(gcloud config get-value project)
SA="stockquote@$PROJECT_ID.iam.gserviceaccount.com"

gcloud beta functions deploy stock-quotes \
  --gen2 --region us-west1 \
  --runtime python39 \
  --trigger-http  \
  --entry-point stock_quotes \
  --source $FUNCTION_DIR \
  --service-account=$SA \
  --set-env-vars SECRET_MANAGER_PROJECT_ID=$PROJECT_ID,SECRET_NAME_YH_API_KEY=X-RapidAPI-Key,BUCKET=$PROJECT_ID \
  --set-env-vars SECRET_NAME_REFRESH_TOKEN=TradeStation_RefreshToken,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret \
  --set-env-vars FOLDER=quotes,PROJECT_ID=$PROJECT_ID --quiet &

gcloud beta functions deploy execute-trade \
  --gen2 --region us-west1 \
  --runtime python39 \
  --trigger-http --quiet \
  --entry-point execute_trade \
  --source $FUNCTION_DIR \
  --service-account=$SA \
  --set-env-vars BUCKET=$PROJECT_ID,FOLDER=quotes,PROJECT_ID=$PROJECT_ID,SECRET_MANAGER_PROJECT_ID=$PROJECT_ID \
  --set-env-vars SECRET_NAME_REFRESH_TOKEN=TradeStation_RefreshToken,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret &

gcloud beta functions deploy get-authorization-code \
  --gen2 --region us-west1 --runtime python39 --trigger-http \
  --entry-point get_authorization_code --source $FUNCTION_DIR \
  --service-account=$SA --quiet --allow-unauthenticated \
  --set-env-vars SECRET_MANAGER_PROJECT_ID=$PROJECT_ID,SECRET_NAME_CLIENT_ID_SECRET=TradeStation_Client_ID_Secret,PROJECT_ID=$PROJECT_ID &

#gcloud scheduler jobs create http get-quotes --schedule="0 15 * * 1-5" --location us-west1 \
#--uri="https://$FUNC_URL/?tickers=QQQ,ONEQ,IVV,VOO,JETS,VHT,VDE,VFH,VTWO,BRK-B,ACN,AMD,GOOGL,AMZN,MSFT,MRVL,FB,QCOM,CRM,SNAP,TSM,BHP,RIO,EXPE,BKNG,HD,NIO,NVDA" \
#--http-method=POST --oidc-service-account-email=smart-invest-func-invoker@$PROJECT_ID.iam.gserviceaccount.com \
#--oidc-token-audience=https://$FUNC_URL &
