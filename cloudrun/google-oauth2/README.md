# Google Cloud Platform Authentication Python Sample  

A python microservice sample application that uses Google Cloud Authentication to call other Google 
Cloud API on behalf of user Google accounts. The python microservice ist e OAuth client registered at 
https://console.developers.google.com/apis/credentials/oauthclient. You mostly likely need to have  project
editor role to create and manage OAuth client

## Getting Started

### Set up the local development environment

Create a python virtual environment with

`python3 -m venv google-oauth2`

#### Configure environment variables  

0. OAUTHLIB_INSECURE_TRANSPORT 1 # allows redirect URI to be http instead of https
0. CLIENT_SECRET
0. CLIENT_ID
0. GOOGLE_APPLICATION_CREDENTIALS

In Pycharm, right click on the line of app.run(debug=True), select debug, expect error,
then add the environment variables in the Debug configuration.

### Prerequisites

0. Pycharm needs to be greater than or equal to  2020.1
0. Python >= 3.7
0. The cloud build service account has Cloud Run admin role to deploy to Cloud Run
0. The service account for Cloud Run has Logs writer role

### Installation and deployment
Clone the code to your cloud source repository. With Cloud build trigger
configured, pushing to the cloud source repository will trigger the
build and deployment to Cloud Run. Verify Cloud Run is enabled in your
project. Create a secret called oauth2_client_secret_oauth2session. Grant the cloud build service account
secret accessor role. Change the following section in cloudbuild.yaml

```
1 gcloud secrets versions access latest --secret="oauth2_client_secret_oauth2session" > /secrets/client_secret.txt
2 --update-env-vars CLIENT_SECRET=$(cat /secrets/client_secret.txt)
3 --update-env-vars CLIENT_ID=
```

0. Find the text in Line 1 from cloudbuild.yaml, understand the command pipes the client secret value to
a text file. The next build step reads the value and set the environment variable.
It's recommended to save client secret in secret manager.
0. Find the text in Line 3 from cloudbuild.yaml, change the value after the `=` sign to the client ID. 
0. Configure [Authorized JavaScript origins](https://console.developers.google.com/apis/credentials)
 to be https://DEPLOYED_CLOUD_RUN_URL and http://YOUR_HOME_IP:5000
0. Configure [Authorized redirect URIs](https://console.developers.google.com/apis/credentials)
 to be https://DEPLOYED_CLOUD_RUN_URL/callback and http://YOUR_HOME_IP:5000/callback
0. Update the configured redirect URL in the python code per local debugging and production deployment server's URL
```python
if os.environ.get('LOCAL_DEBUG'):
    redirect_uri = 'http://hil.freeddns.org:5000/callback'
else:
    redirect_uri = 'https://googleoauth2-zro2itatnq-uc.a.run.app/callback'
```
## Running the tests
0. Open the latest Chrome browser and hit http://YOUR_HOME_IP:5000/login
0. You should be redirected to Google account sign-in page or select an existing Google account
0. Grant the app necessary permissions
0. Redirected back to the app's /callback URI shows the access_token with 200 

### URL endpoints
- `/zones/projects/<project_id>` lists the compute engine zones in project_id
- `/zones` lists the compute engine zones in the project where the app is hosted
- `/sampleentry` shows data catalog entries on public datasets
- `/entry/projects/<project_id>/datasets/<dataset>/tables/<table>` shows data catalog entries on specific datasets 

## License

This project is licensed under the MIT License
