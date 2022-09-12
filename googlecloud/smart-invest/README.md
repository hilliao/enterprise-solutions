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