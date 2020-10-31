#!/bin/bash

# set Cloud SQL password and store it in secret manager
set -e # exit the script when execution hits any error
#set -x # don't print the executing lines to reveal secrets

export SECRET_PROJECT_ID=
export SQL_PROJECT_ID=
export SQLUSER=hil
export SQLINSTANCEID=test-psql

export PASSWORD=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 10 | head -n 1 | tr -d '\n')
export SECRET="SQL_${SQLINSTANCEID}_${SQLUSER}"

# set Cloud SQL user password
gcloud sql users set-password $SQLUSER --instance=$SQLINSTANCEID --password=$PASSWORD \
  --host=% --project $SQL_PROJECT_ID

# persist the password in sercret manager
gcloud config set project $SECRET_PROJECT_ID

# try to access the secret; if it does not exist, create one
gcloud secrets versions access latest --secret=$SECRET > /dev/null || \
gcloud secrets create $SECRET --replication-policy="automatic"

# add the password to the latest version of the secret
echo $PASSWORD | gcloud secrets versions add $SECRET --data-file=-
