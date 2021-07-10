# Infrastructure as code to create a GKE cluster of high CIS benchmark score

## Overview
Creating a GKE cluster in Google cloud with default values already yields high [GKE CIS benchmark](https://cloud.google.com/kubernetes-engine/docs/concepts/cis-benchmarks) scores.
Using the REST button in the cloud console's create a new GKE cluster page produces most of the JSON content for the
deployment manager template under `'properties':`

## inspect the deployment yaml file
There are multiple properties in the deployment yaml file for creating the GKE cluster such as `gke-name`.
The deployment python template references the value of the properties by `context.properties['gke-name']`.
Inspect the properties and identify the correct values for creating a GKE cluster in your project.

## Set the properties with environment variables
The command `envsubst < "gke.yaml"` replaces the environment variables with their values in the deployment yaml.
For example, `$GKE_NAME` is replaced with the name of the GKE cluster you want to create. You must export the 
environment variables before executing the `envsubst` command; otherwise, empty string will replace all variables.

## Test the deployment
Follow the comment in the deployment yaml file to export the environment variable values. For example,
execute the following command to generate gke-filled.yaml

```shell
export GKE_NAME=hil-dm-0 && export ZONE=us-west1-c && export REGION=us-west1 # <OMITTED>
envsubst < "gke.yaml" > "gke-filled.yaml"
gcloud deployment-manager deployments create hil-gke-0 --config gke-filled.yaml
```

The command creates the deployment and thus the GKE cluster. Once the deployment succeeds without errors,
Proceed to create a cloud build trigger.

## Create the CI CD pipelines
The shell script creates a cloud build trigger. To use Cloud build, bind `Deployment Manager Editor IAM` role
 to the cloud build service account in the project to create the deployment. The build trigger by default uses cloud source repository. 
Modify the environment variables in the `build-triggers-*.sh`according to how you push the source to the project's
cloud source repository such as `BRANCH`, `REPO_NAME`.

### cloud build configuration file
`cloudbuild-*.yaml` has the build steps. The 1st step exports environment variables and executes `envsubst` to replace
vallues saved to /workspace/*.yaml to be consumed in the next build steps. The build step of creating the deployment 
first checks if the deployment exists. If yes, it updates the deployment; otherwise, it creates the deployment.

```shell
(gcloud deployment-manager deployments describe $_DEPLOYMENT_NAME && gcloud deployment-manager deployments update \
$_DEPLOYMENT_NAME --config $YAML) || gcloud deployment-manager deployments create $_DEPLOYMENT_NAME --config $YAML
```

The command above creates the deployment in the same project as the cloud build. To create deployments in other projects,
pass the --project to all gcloud commands.