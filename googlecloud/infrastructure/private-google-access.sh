#!/bin/bash
# Copyright 2021 GoogleCloud.fr; All rights reserved! Execute at your own risk as there's no warranty!
#
# configure private Google access in Cloud DNS with most Google API domains under these circumstances:
#   You don't use VPC Service Controls.
#   You do use VPC Service Controls, but you also need to access Google APIs and services that are not supported by VPC Service Controls.
#
# verify no existing DNS zones of the domains exist to prevent conflicts
# The goal is to automate the manual steps at https://cloud.google.com/vpc/docs/configure-private-google-access#config-domain
# VPC network route configuration is missing from the script. refer to https://cloud.google.com/vpc/docs/configure-private-google-access#config-routing

set -e # exit the script when execution hits any error
set -x # print the executing lines

PROJECT_ID=[REQUIRED_FIELD]
NETWORK=[REQUIRED_FIELD]

declare -a domains=("googleadapis.com" "ltsapis.goog" "gcr.io" "pkg.dev" "gstatic.com" "appspot.com" "cloudfunctions.net" "pki.goog" "cloudproxy.app" "run.app" "datafusion.googleusercontent.com" "datafusion.cloud.google.com" "notebooks.cloud.google.com" "notebooks.googleusercontent.com" "appengine.google.com" "packages.cloud.google.com" "source.developers.google.com")

# 199.36.153.8/30 has 4 IPs per https://cloud.google.com/vpc/docs/configure-private-google-access#config
IPs="199.36.153.8 199.36.153.9 199.36.153.10 199.36.153.11"

# create a Cloud DNS managed zone containing the A record [--type=A] for private.googleapis.com
gcloud beta dns --project=$PROJECT_ID managed-zones create googleapis --description="https://cloud.google.com/vpc/docs/configure-private-google-access#config" --dns-name="googleapis.com." --visibility="private" --networks=$NETWORK && \
gcloud beta dns --project=$PROJECT_ID record-sets transaction start --zone=googleapis
gcloud beta dns --project=$PROJECT_ID record-sets transaction add private.googleapis.com. --name=\*.googleapis.com. --ttl=300 --type=CNAME --zone=googleapis
gcloud beta dns --project=$PROJECT_ID record-sets transaction execute --zone=googleapis
gcloud beta dns --project=$PROJECT_ID record-sets transaction start --zone=googleapis
gcloud beta dns --project=$PROJECT_ID record-sets transaction add $IPs --name=private.googleapis.com. --ttl=300 --type=A --zone=googleapis
gcloud beta dns --project=$PROJECT_ID record-sets transaction execute --zone=googleapis

# create a Cloud DNS managed zone containing the CNAME record [--type=CNAME] per domain
for domain in "${domains[@]}"
do
    # replace . with - for zone names; e,g, googleadapis.com -> googleadapis-com as cloud DNS does not allow zone name with .
    NAME=$(echo $domain | tr . -)

    gcloud beta dns --project=$PROJECT_ID managed-zones create $NAME --description="https://cloud.google.com/vpc/docs/configure-private-google-access#config" --dns-name="$domain." --visibility="private" --networks=$NETWORK && \
    gcloud dns --project=$PROJECT_ID record-sets transaction start --zone=$NAME && \
    gcloud dns --project=$PROJECT_ID record-sets transaction add $IPs --name=$domain. --ttl=300 --type=A --zone=$NAME && \
    gcloud dns --project=$PROJECT_ID record-sets transaction execute --zone=$NAME && \
    gcloud dns --project=$PROJECT_ID record-sets transaction start --zone=$NAME && \
    gcloud dns --project=$PROJECT_ID record-sets transaction add $domain. --name=\*.$domain. --ttl=300 --type=CNAME --zone=$NAME && \
    gcloud dns --project=$PROJECT_ID record-sets transaction execute --zone=$NAME || exit $?
done