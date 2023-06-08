# Smart Investment Solution with Brokerage integration

The solution intends to implement common algorithm based investment strategies deployed in Google cloud.
Most fintech startups don't have applications that support API based trade order execution. Major brokerage firms such as
Goldman Sachs or Fidelity only expose the trading APIs to their institutional clients. The solution needs to depend on
brokerage firms that expose the trading API. Thus, trade station has been chosen to implement the execute_trade_order
function.

## Objective

1. Minimize operational costs by using Google cloud serverless products. 
2. Allow users to create custom algorithms in Python modules to execute trades.
3. API driven trade execution based on the custom trading algorithms users create.
4. Secure API endpoints with Open ID connect ensure enterprise grade security and Cloud scheduler integration.
5. High availability and resiliency at 99.95% powered by Google cloud run or cloud function gen2

# Functional requirements

Users login once to store the refresh token in Google cloud secret manager. Trade executions are implemented via 
Cloud Function and secure by Google Cloud IAM. Users configure cloud scheduler to invoke cloud function with a 
service account granted Cloud Function invoker on the invoked cloud function and Cloud Run invoker on the function's
Cloud Run service. 

# Deployment Handbook
setup.sh creates the infrastructure required to run the microservices. deploy.sh executes commands to deploy
the cloud functions. Replace mandatory variables in setup.sh such as PROJECT_ID and region in the scripts.

## setup.sh
Cloud functions are regional project scoped resources.
Execute each command sequentially and make sure the current commands succeed. Some commands have dependencies
causing simultaneous execution or execution out of order problematic. After all commands in setup.sh succeeds, there
are some manual steps such as adding secrets required for cloud functions to return success.

## cloud-function/deploy.sh
The gcloud commands to deploy functions gen2 can be executed in parallel. FUNCTION_DIR is the absolute path to
cloud-function. There are some hard coded strings such as smart-invest that depends on the service account
creation command in setup.sh.

## Debugging cloud function locally
Create a Python virtual environment in Pycharm. Install the packages in requirements.txt.
Refer to [the guide](https://github.com/GoogleCloudPlatform/functions-framework-python)
to configure executing functions-framework locally to debug in PyCharm community edition. I've succeeded
in stepping through the code. Refer to the screenshot of PyCharm's run,debug configurations in `python-debug-functions-framework.png`. 
Basically, in run,debug configuration, under configuration, change from script path to module name. Click on the
3 dots to locate the functions-framework module. You'd need to type it to check if it exists. Enter the parameters:
--target stock_quotes --port 8081 --debug where stock_quotes is the function name and 8081 is an unused port on local.
Set the working directory to the directory of the function's filename.

### Environment Variables
* BUCKET=[Created bucket name to store stock quotes]
* FOLDER=[GSC bucket's folder to store quote .json files]
* PROJECT_ID=[Google Cloud Project ID]
* SECRET_MANAGER_PROJECT_ID=[Project ID for secret manager]
* SECRET_NAME_CLIENT_ID_SECRET=[Secret manager's secret name that stores Trade Station's client ID and secret separated by ,]
* SECRET_NAME_REFRESH_TOKEN=[Secret manager's secret name that stores Trade Station's refresh token]
* SECRET_NAME_YH_API_KEY=[Secret manager's secret name that stores the Yahoo Finance API key]