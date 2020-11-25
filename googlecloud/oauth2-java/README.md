# Java sample OAuth2 application to access user data in Google Cloud 

A microservice Spring Boot REST API that asks users for perimssions to list user's bigquery datasets

## Getting Started

### Set up the local development environment

Intellij should recognize the directory as a gradle project. Set Java version 

0. Settings > Build, Execution, Deployment > Build Tools > Gradle > Gradle JVM to Java 11
0. Settings > Build, Execution, Deployment > Compiler > Java Compiler > Project bytecode version to 11

If no error occurs, the Run/Debug configurations on the menu should show you a debug button.
 If none shows, create a Spring Boot application in Run/Debug configurations.
  Click the run or debug button to start the spring boot application.

### Prerequisites

0. Intellij needs to be greater than or equal to  2020.1
0. Intellij has Java 11 installed
0. Create [web client id and secret](https://console.cloud.google.com/apis/credentials) per
 [Integrating Google Sign-In into your web app](https://developers.google.com/identity/sign-in/web/sign-in)
0. The service account in the deployed Cloud Run service or in Intellij debug configuration's
 GOOGLE_APPLICATION_CREDENTIALS environment variable needs the following predefined roles for 
 Cloud debug, logging, trace to function.
    - Cloud Debugger Agent
    - Cloud Trace Agent
    - Errors Writer
    - Logs Writer

### Installing
Clone the code to your cloud source repository. With Cloud build trigger
configured, pushing to the cloud source repository will trigger the
build and deployment to Cloud Run. Verify Cloud Run is enabled in your
project.

Add [--service-account parameter](https://cloud.google.com/sdk/gcloud/reference/run/deploy#--service-account) to 
`gcloud run deploy` and specify a Google service account with recommended roles in cloudbuild.yaml. Otherwise,
compute engine default service account will be used.
 For Cloud run related customization, substitute the following in the build trigger:

0. $_SVC_NAME > the Cloud run service name in build trigger.
0. $_SECRET_PROJECT > The project ID of the secret manager which stores [Google OAuth2 client ID, secret](https://console.cloud.google.com/apis/credentials)
0. $_CLIENT_SECRET > the secret name of Google OAuth2 client secret
0. $_CLIENT_ID > the secret name of Google OAuth2 client ID
0. $_CALLBACK_URL > the OAuth2 callback URL configured in [Google OAuth2 client ID, secret](https://console.cloud.google.com/apis/credentials)

Bind secret accessor role to the cloud build service account. Otherwise cloud build will fail to access secrets.

0. Configure [Authorized JavaScript origins](https://console.developers.google.com/apis/credentials)
 to be https://DEPLOYED_CLOUD_RUN_URL and http://YOUR_HOME_IP:5000
0. Configure [Authorized redirect URIs](https://console.developers.google.com/apis/credentials)
 to be https://DEPLOYED_CLOUD_RUN_URL/callback and http://YOUR_HOME_IP:5000/callback

## Running the basic tests
0. Open the latest Chrome browser and hit http://YOUR_HOME_IP:8080/login
0. You should be redirected to Google account sign-in page or select an existing Google account
0. Grant the app necessary permissions

## Post Deployment Tests 

Refer to code `@GetMapping` to execute curl with once user is logged in.
  
Inspect the Cloud trace, Cloud Debugger, Cloud Logging to see invoking
the endpoints create the trace, logs, and an active debugging
application. the latency for the trace or logs to show is usually 2
minutes; setting a snapshot in the Cloud Debugger and hitting the
endpoint may not catch a snapshot right away. Maybe there was some lag.
It's usually the 2nd time of hitting the endpoint to catch the snapshot.

## License

This project is licensed under [Apache License, Version 2.0 (Apache 2.0)](http://www.apache.org/licenses/LICENSE-2.0)

## Known issues
GoogleAuthorizationCodeFlow needs to execute .setApprovalPrompt("force") for credential.getRefreshToken()
to return a valid refresh token. Otherwise, getRefreshToken returns null and GoogleCredentials gCredentials = UserCredentials.newBuilder()
throws exceptions. [Official Google Cloud BigQuery user authentication doc](https://cloud.google.com/bigquery/docs/authentication/end-user-installed)
uses AuthorizationCodeInstalledApp to create Credential and credential.getRefreshToken() would return a valid refresh credential.
There is no easy Java client library to Exchange an authorization code for a refresh token. If a workaround is developed,
developer can delete .setApprovalPrompt("force") for a better user experience where user does not need to approve 
Authorization scope request at each login.