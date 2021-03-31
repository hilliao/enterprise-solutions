#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines


NAME="${PWD##*/}-gke"
REPO_NAME=helloworld
BRANCH=gke
REPO_PATH="deployment-manager"

gcloud beta builds triggers create cloud-source-repositories \
    --repo=$REPO_NAME --name=$NAME \
    --branch-pattern="^$BRANCH$" \
    --build-config="$REPO_PATH/cloudbuild-dm-gke.yaml" \
    --included-files="$REPO_PATH/**" \
    --ignored-files="**/README.md" \
    --substitutions _DEPLOYMENT_NAME=hil-9,_GKE_NAME=hil-dm-9,_ZONE=us-west1-c,_REGION=us-west1,_VPC=hil-vpc,_SUBNET=hil-vpc,_CLUSTER_IPV4_RANGE=10.72.0.0/14,_SERVICES_IPV4_RANGE=10.68.16.0/20,_MASTER_IPV4_RANGE=172.22.32.0/28,_DM_DIR=googlecloud/gke-config-sync/deployment-manager