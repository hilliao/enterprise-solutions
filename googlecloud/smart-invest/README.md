# Smart Investment Solution with Brokerage integration

The solution intends to implement common algorithm based investment strategies deployed in Google cloud.
Most fintech startups don't have applications that support API based trade order execution. Major brokerage firms such as
Goldman Sachs or Fidelity only expose the trading APIs to their institutional clients. The solution needs to depend on
brokerage firms that expose the trading API. Thus, trade station has been chosen to implement the execute_trade_order
function.

## Objective

0. Minimize operational costs by using Google cloud serverless products. 
1. Allow users to create custom algorithms in Python modules to execute trades.
2. API driven trade execution based on the custom trading algorithms users create.
3. Secure API endpoints with Open ID connect ensure enterprise grade security and Cloud scheduler integration.
4. High availability and resiliency at 99.95% powered by Google cloud run or cloud function gen2

# Functional requirements

Users login once to store the refresh token in Google cloud secret manager. Trade executions are implemented via 
Cloud Function and secure by Google Cloud IAM. Users configure cloud scheduler to invoke cloud function with a 
service account granted Cloud Function invoker on the invoked cloud function and Cloud Run invoker on the function's
Cloud Run service. 