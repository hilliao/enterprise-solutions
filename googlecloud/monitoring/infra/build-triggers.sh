#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines


NAME=${PWD##*/}
REPO_NAME=github
BRANCH=master
REPO_PATH="googlecloud/${PWD##*/}"
PROJECT_ID=`echo enter project id`


gcloud beta builds triggers create cloud-source-repositories \
    --repo=$REPO_NAME --name=$NAME \
    --branch-pattern="^$BRANCH$" \
    --build-config="$REPO_PATH/cloudbuild.yaml" \
    --included-files="$REPO_PATH/**" \
    --ignored-files="**/README.md,$REPO_PATH/infra/**,**/unittests.py" \
    --substitutions _CLOUD_RUN_SVC_NAME=$NAME,_GCP_SA=monitoring-viewer,_MAX_THREADS=10,_MON_PROJECT_ID=$PROJECT_ID \
    --project $PROJECT_ID