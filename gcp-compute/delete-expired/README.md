# Delete expired compute engine instances and instance group with certain metadata
DevOps team wants to have an automated method to delete instances and instance groups with certain criteria. Google cloud compute engine instance metadata is used to indicate the expiry date or datetime to delete the instances, a good example to automate toil in SRE.

## Configuration
Look for the fist few lines of UPPER CASE variable names below the import statements in [main.py](https://github.com/hilliao/enterprise-solutions/blob/308b34948fa42d55aba8c3c63311b32b42f25c43/gcp-compute/main.py). E,g,
- METADATA_EXPIRY = 'expiry'
- METADATA_EXPIRY_1 = 'expiry-1'
- METADATA_INSTANCE_GROUP = 'instance-group'
- INSTANCE_TEMPLATE_STARTS_WITH = 'usb-gce-presto'

## Prerequisites
Cloud scheduler service initialization requires project owner role. It's
an one time task. The Cloud pub/sub and function creation don't require
project owner or editor roles.

## Cloud Function
main.py is the cloud function python code to delete expired instances.
Instances with custom metadata of **expiry** or **expiry-1** is set to
the following format for the python code to parse. When Cloud Function
executes, expired instances are deleted. If those instances have custom
metadata **instance-group** set to an instance group, the group is deleted. 

- expiry uses python datetime format: *DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'*
- example: *2019-11-22 13:38:19.581781*
- expiry-1 uses date format and is set to expire by the end of the day:
  *DATE_FORMAT = '%Y-%m-%d'* 
- example: *2019-11-22* expires at 2019-11-23 00:00:00.000000

Any instance group templates starts with usb-gce-presto are deleted. If
the template is used in any instance groups, deletion does not happen.

## Recommended IAM roles for the service account or user to deploy the solution 

- Cloud Functions Admin or roles/cloudfunctions.developer
- Cloud Scheduler Admin
- Compute Instance Admin (beta)
- Service Account User
- Pub/Sub Admin or roles/pubsub.editor

## Commands to run for creating cloud scheduler, pub/sub topic, function
infra-setup.sh at commit 5bbfd552c137e4f7a642fa24e031975578c33316 is not
ready for production use. Do not run the whole script but pick
individual commands to execute and inspect the command output before
proceeding. Resolve any errors and do not blindly run all commands.

## CI, CD
**cloudbuild.yaml** is the Cloud build continuous deployment build
definition to create automated deployment. Follow
[Sending build notifications](https://cloud.google.com/cloud-build/docs/send-build-notifications)
for build result notification.

## Developer Guide
Use Pycharm with run/debug profile and set environment variable
GCLOUD_PROJECT to be the Google Cloud project ID. Run the following
command to activate application default credential as the Google cloud
identity (not recommended)

$ [gcloud auth application-default login](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login)

Alternatively, set
[GOOGLE_APPLICATION_CREDENTIALS](https://cloud.google.com/docs/authentication/production)
environment variable as Google recommended DevOps approach. 
