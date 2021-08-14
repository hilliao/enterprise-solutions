# Google GKE blueprint
This blueprint creates a GKE cluster.
Use [the private catalog](https://github.com/hilliao/enterprise-solutions/tree/master/googlecloud/infrastructure/deployment-manager/private-catalog)
solution to create a console experience which creates a new git cloud source repository, a cloud build trigger 
which connects to it. The cloud build trigger allows entering values for common GKE cluster creation parameters.

## Set the values in setters.yaml, gke.yaml:
The cloudbuild*.yaml executes export bash commands to replace environment variables in gke.yaml, setters.yaml
with the cloud build trigger environment variable substitutions.
