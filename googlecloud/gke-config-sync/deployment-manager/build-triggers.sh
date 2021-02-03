#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines


NAME="${PWD##*/}-vpc"
REPO_NAME=
BRANCH=master
REPO_PATH="googlecloud/gke-config-sync/deployment-manager"

gcloud beta builds triggers create cloud-source-repositories \
    --repo=$REPO_NAME --name=$NAME \
    --branch-pattern="^$BRANCH$" \
    --build-config="$REPO_PATH/cloudbuild.yaml" \
    --included-files="$REPO_PATH/**" \
    --ignored-files="**/README.md" \
    --substitutions _DEPLOYMENT_NAME=hil-vpc