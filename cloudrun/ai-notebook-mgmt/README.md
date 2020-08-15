# Google AI platform notebook instance management, OAuth2 sample solution

A microservice deployed in Google Cloud Run that manages Google cloud AI platform notebook
instances

## Getting Started

### Set up the local development environment

Intellij should recognize the directory as a gradle project. Set Java version 
0. Settings > Build, Execution, Deployment > Build Tools > Gradle > Gradle JVM to Java 11
0. Settings > Build, Execution, Deployment > Compiler > Java Compiler > Project bytecode version to 11

If no error occurs, the Run/Debug configurations  on the menu  should show you a debug button.
Click the run or debug button to start the spring boot application.

### Prerequisites

0. Intellij needs to be greater than or equal to  2020.1
0. Intellij has Java 11 installed
0. The Google account user has AI Platform notebook admin role
0. The service account for Cloud Run needs the following predefined roles for Cloud debug, trace to function.
0. Create [web client id and secret](https://console.cloud.google.com/apis/credentials) per
 [Integrating Google Sign-In into your web app](https://developers.google.com/identity/sign-in/web/sign-in)
0. The other predefined roles recommended:
    - Cloud Debugger Agent
    - Cloud Trace Agent
    - Errors Writer
    - Logs Writer

### Installing
Clone the code to your cloud source repository. With Cloud build trigger
configured, pushing to the cloud source repository will trigger the
build and deployment to Cloud Run. Verify Cloud Run is enabled in your
project. Change the following section in cloudbuild.yaml
for Cloud run related customization. Replace [paste your web client id here]

```
- name: 'gcr.io/cloud-builders/gcloud'
  gcloud run deploy ai-notebook-mgmt ... --update-env-vars CLIENT_SECRET=$(cat /secrets/client_secret.txt) \
--update-env-vars CLIENT_ID=[paste your web client id here]
```
#### installing client secret
0. Create a secret with specified name `oauth2_client_secret_oauth2bigquery_java` in cloudbuild.yaml to store the client secret
0. Configure the cloud build service account to have secret accessor role

#### Configure redirect URL in the code
Set the redirect or callback URL per local debugging and production deployment server's URL 
```java
static {
    if (System.getenv("LOCAL_DEBUG") != null) {
        CALLBACK_URL = "http://hil.freeddns.org:8080/callback";
    } else {
        CALLBACK_URL = "https://ai-notebook-mgmt-zro2itatnq-uc.a.run.app/callback";
    }
```

## Running the basic tests
Call the /sleep?seconds=0 endpoint to see if 200 is returned
```
curl localhost:8080/sleep?seconds=0
curl https://$CLOUD_RUN_URL/sleep?seconds=0 -k
```
In Chrome, view http://YOUR_HOME_IP:8080/login to test locally

## Post Deployment Tests 

use the following JSON request body 
```

curl --request POST \
  --url http://localhost:8080/createAINotebook \
  --header "authorization: $(gcloud auth print-access-token)" \
  --header 'content-type: application/json' \
  --data '{
          	"projectId"	: "project ID to create the AI platform notebooks in",
          	"instanceName":"my-ai-notebook-0",
          	"VPCProjectId":"The shared VPC host project ID",
          	"VPCName":"Shared VPC name or default",
          	"subnetName":"subnet in the VPC such as default",
          	"region":"Google cloud region",
          	"zone":"Google cloud zone"
          }'
```
In Chrome, view [https://DEPLOYED_CLOUD_RUN_URL/login](https://ai-notebook-mgmt-zro2itatnq-uc.a.run.app/login) to test.

Inspect the Cloud trace, Cloud Debugger, Cloud Logging to see invoking
the endpoints create the trace, logs, and an active debugging
application. the latency for the trace or logs to show is usually 2
minutes; setting a snapshot in the Cloud Debugger and hitting the
endpoint may not catch a snapshot right away. Maybe there was some lag.
It's usually the 2nd time of hitting the endpoint to catch the snapshot.

## License

This project is licensed under the MIT License

## Known issues
GoogleAuthorizationCodeFlow needs to execute .setApprovalPrompt("force") for credential.getRefreshToken()
to return a valid refresh token. Otherwise, getRefreshToken returns null and GoogleCredentials gCredentials = UserCredentials.newBuilder()
throws exceptions. [Official Google Cloud BigQuery user authentication doc](https://cloud.google.com/bigquery/docs/authentication/end-user-installed)
uses AuthorizationCodeInstalledApp to create Credential and credential.getRefreshToken() would return a valid refresh credential.
There is no easy Java client library to Exchange an authorization code for a refresh token. If a workaround is developed,
developer can delete .setApprovalPrompt("force") for a better user experience where user does not need to approve 
Authorization scope request at each login.