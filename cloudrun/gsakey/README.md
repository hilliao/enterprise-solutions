# Google service account key management solution

A simple microservice deployed in Google Cloud Run that manages an
existing Google service account's keys. Initial implementation contains
GET to list the keys, POST to craete the keys and store in secret
manager, DELETE to remove keys but may not delete the version from
secret manager.

## Getting Started

### Set up the local development environment

Create a Google service account from the project you intend to deploy
the Cloud run solution to. Generate a JSON key file.
0. set GOOGLE_APPLICATION_CREDENTIALS environment variable to that key
   file's path
1. set GCP_PROJECT environment variable to the Google cloud Project ID
2. Bind the follwoing roles to the Google service account: \[Cloud
   Debugger Agent, Cloud Trace Agent, Errors Writer, Service Account Key
   Admin, Logs Writer, Secret Manager Admin\]
3. The Secret Manager Admin role should be set in the
   secret_manager_project_id which may not be the same project as the
   Google service account.
4. Replace the argument after *--service-account* in cloudbuild.yaml
   with the Google service account.
5. Enable Cloud build service account with Cloud Run Admin role at https://console.cloud.google.com/cloud-build/settings/service-account
6. Configure Cloud build trigger wit the source repository. Choose file
   type in Build configuration: Cloud build configuration file at
   cloudrun/gsakey/cloudbuild.yaml
7. Bind Cloud Run invoker role to the developer or operation team who
   invoke the Cloud Run service.

### Prerequisites

Python 3.8 requirements.txt shows required Python modules for the app to
run. Example python development environment creation steps:

```
$ python3 -m venv cloudrun/gsakey/
$ . cloudrun/gsakey/bin/python
$ python --version # verify the python version is 3.x
$ pip install -r cloudrun/gsakey/requirements.txt
```
If PORT environment variable is not set, app will run on 8080. Make sure
the port is free to use. The main module is
/cloudrun/gsakey/managekey.py which you should select in Pycharm's debug
configuration.
### Installing
Clone the code to your cloud source repository. With Cloud build trigger
configured, pushing to the cloud source repository will trigger the
build and deployment to Cloud Run. Verify Cloud Run is enabled in your
project. Change the following section in cloudrun/gsakey/cloudbuild.yaml
for Cloud run related customization.

```
- name: 'gcr.io/cloud-builders/gcloud'
  args: ['run', 'deploy'
```

## Running the tests
Import CloudRunGSAKeyManager.postman_collection.json into Postman for
easy invocation of the REST methods.
1. set {{url}} to the cloud run url including https://
2. set {{access_token}} to the output of gcloud auth
   print-identity-token from the Google Account with Cloud Run invoker
   role bound to the cloud run service.

### Break down into end to end tests

Call the health endpoint
use postman or
```
curl --request GET 'https://gsakeymanager-uc.a.run.app/health' \
--header 'Authorization: Bearer token'
```
call the GET endpoint with an existing Google service account in the
project where the service account of the Cloud Run service has access to
through Service account admin role use postman or
```
curl --request GET \
'https://gsakeymanager-uc.a.run.app/gsakey/hil-test@[PROJECT_ID].gserviceaccount.com' \
 --header 'Authorization: Bearer token'
```
call the POST endpoint to create a service account key for the service
account set in the request body in postman or
```
curl  --request \
POST 'https://gsakeymanager-uc.a.run.app/gsakey'  --header \
'Authorization: Bearer token' --form \
'gsa=hil-test@[PROJECT_ID].iam.gserviceaccount.com'  --form \
'secret_name=tmp-test-secret-0'  --form \
'secret_manager_project_id=[SECRET_PROJECT_ID]'
```
call the DELETE endpoint to delete the new service account key in
postman or
```
curl  --request DELETE \
'https://gsakeymanager-uc.a.run.app/gsakey'  --header \
'Authorization: Bearer token'  --form \
'gsa-key-names=projects/[PROJECT_ID]/serviceAccounts/hil-test@[PROJECT_ID].iam.gserviceaccount.com/keys/1e6fd4742829594a848e3f5e1e9c82872ddd54df'
```

## Deployment

Inspect the Cloud trace, Cloud Debugger, Cloud Logging to see invoking
the endpoints create the trace, logs, and an active debugging
application. the latency for the trace or logs to show is usually 2
minutes; setting a snapshot in the Cloud Debugger and hitting the
endpoint may not catch a snapshot right away. Maybe there was some lag.
It's usually the 2nd time of hitting the endpoint to catch the snapshot.

## License

This project is licensed under the MIT License