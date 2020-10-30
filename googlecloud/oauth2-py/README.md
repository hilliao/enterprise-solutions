# Python sample OAuth2 application to access user data in Google Cloud  

The python flask microservice sample OAuth2 application calls other Google 
Cloud API on behalf of user Google accounts. The python microservice has OAuth2 client registered at 
https://console.developers.google.com/apis/credentials/oauthclient. Administrators likely need to have project
editor role to create and manage OAuth clients.

## Getting Started

### Set up the local development environment

Create a python virtual environment with

`python3 -m venv $SOURCE_DIR`

#### Configure environment variables  

The follwoing are required environment variables to develop and debug the application. OAUTHLIB_INSECURE_TRANSPORT is 
required for the redirect URI to have http such as http://localhost:5000/callback

0. OAUTHLIB_INSECURE_TRANSPORT set to 1
0. CLIENT_SECRET
0. CLIENT_ID
0. GOOGLE_APPLICATION_CREDENTIALS needs 
0. CALLBACK_URL set to `http://localhost:5000/callback` for local debugging

In Pycharm, right click on the line of app.run(debug=True), select debug, expect error,
then add the environment variables in the Debug configuration.

### Prerequisites

0. Pycharm needs to be greater than or equal to  2020.1
0. Python >= 3.7
0. The cloud build service account has Cloud Run admin role to deploy to Cloud Run
0. The service account for Cloud Run has `Logs writer` predefind role

### Installation and deployment
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

## Running the tests
0. Open the latest Chrome browser and hit http://YOUR_HOME_IP:5000/login
0. You should be redirected to Google account sign-in page or select an existing Google account
0. Grant the app necessary permissions
0. Redirected back to the app's /callback URI shows the access_token with 200 

### URL endpoints
Refer to code `@app.route` to execute curl with once user is logged in.

## License

This project is licensed under [Apache License, Version 2.0 (Apache 2.0)](http://www.apache.org/licenses/LICENSE-2.0)
