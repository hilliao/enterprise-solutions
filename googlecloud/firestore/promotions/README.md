# Microservice for promotional code management
The idea of businesses giving promotions is to increase sales and reduce inventory.
This microservice uses simple REST API to fulfill the goal

## Google cloud firestore as the backend noSQL
Deploy the microservice Docker container to cloud run or a host like compute engine instances.
Dockerfile is for Clodu run while Dockerfile-SA is for a VM host. Both files have sample commands to 
build and deploy. Refer to cloudbuild.yaml for using cloud build to push the container to artifact registry.

## Create service account to access firestore if deployed on a host
Create a service account with Cloud Datastore User, Logs Writer IAM role in the project if hosted on a VM.
There is no need to create a service account if deployed to cloud run. Grant the IAM roles to the cloud run service account.
For local debugging, create a service account key and set GOOGLE_APPLICATION_CREDENTIALS to the
path of the downloaded .json file.

## Build environment variables with cloud build
 - _BASIC_AUTH: admin password for creating, getting promo codes
 - _IMAGE: container image. e,g, promo-svc-dev:latest
 - _LOCATION: Google cloud region for artifact registry. e,g, us-central1
 - _REPOSITORY: Google cloud artifact registry repo. e,g, promo-svc
 - _SSH_SERVER: The user@host to deploy the container to. e,g, ubuntu@host.example.com

The service account key is stored in a secret in secret manager referenced by **SA_KEY**.
firestore-rw.json filename needs to be the same across cloudbuild.yaml and Dockerfile-SA.
The cloud build step copies the content of the service account key, source files to the folder where the docker container is built.

## run time environment variables
 - PORT=5000
 - BASIC_AUTH: string for admin password
 - PROJECT_ID: Google cloud project ID 
 - FIRESTORE_PROJECT_ID
 - FIRESTORE_PATH: refer to FIRESTORE_PATH in cloudbuild.yaml; e,g, root-collection/document/sub-collection 

## Test the microservice
Install Postman and import the collection.json file to try hitting the REST API
 - /healthz: health check endpoint
 - /promotions: *[more in the *postman_collection.json file]*