# Deployment manager template to create a logs router sink
The python template creates a logs router sink at the organization level with the given log filter string.
If no existing topic is specified in the yaml file, the logs router sink's writer service account is bound
pub/sub publisher role to the new topic.

## configure Google identity platform or workspace audit logs export
User's sign-in events are usually several hours late to show in Admin Console's reports.
Follow [Login audit log](https://support.google.com/a/answer/4580120?hl=en&ref_topic=9027054) 's instructions to
share the audit log data with Google Cloud.

## IAM role binding required
Refer to the python template file's comments for IAM role bindings required for deployment maanager.
In general the deployment manager service account needs to be able to bind pub/sub publisher role in the project
and create logs router sink at the organization level

- Bind Pub/Sub Admin role to the deployment manager service account $PROJECT_NUMBER@cloudservices.gserviceaccount.com in the project
- Bind Logging Admin role to the deployment manager service account $PROJECT_NUMBER@cloudservices.gserviceaccount.com at the organization level

## Command to create the deployment
- Set $YOUR-ORG-LOG-SINK
- Set $PROJECT_ID
- Set values in the yaml file: org_id, name
```shell
gcloud deployment-manager deployments create $YOUR-ORG-LOG-SINK --config org-log-export.yaml --project $PROJECT_ID
```
