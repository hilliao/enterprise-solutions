#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

#TRIGGER_NAME="${PWD##*/}-gke"
REPO_NAME=$CSR_REPO
BRANCH=master
REPO_PATH=$CSR_REPO_PATH # "googlecloud/infrastructure/blueprints"

gcloud beta builds triggers create cloud-source-repositories \
    --repo=$REPO_NAME --name=$TRIGGER_NAME \
    --branch-pattern="^$BRANCH$" \
    --build-config="$REPO_PATH/cloudbuild-gke.yaml" \
    --included-files="$REPO_PATH/**" \
    --ignored-files="**/README.md" \
    --substitutions _GKE_CLUSTER_NAME=hil-blueprints-test,_DEPLOYMENT_NAME=hil-blueprints-test,_GKE_REGION=us-west1,_VPC=default,_SUBNET=default,_POD_IP_RANGE_NAME=gke-hil-pods,_SVC_IP_RANGE_NAME=gke-hil-services,_MASTER_IP_RANGE=172.22.32.0/28,_BLUEPRINTS_DIR=$REPO_PATH,_MACHINE_TYPE=e2-medium,_IF_PREEMPTIBLE=true,_DISK_GB=55 \
    --project $BUILD_PROJECT_ID