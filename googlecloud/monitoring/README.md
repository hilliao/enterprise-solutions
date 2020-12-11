# Google cloud monitoring metric GKE node cpu example

A cloud run microservice that reads monitoring metrics with the filter:
`the metric.type = "kubernetes.io/node/cpu/total_cores" AND resource.type="k8s_node"` in a monitored project

## Getting Started
0. [Bind project owner role to Google APIs service account](https://cloud.google.com/deployment-manager/docs/configuration/set-access-control-resources##granting_permission_to_set_iam_policies)
 in order to create deployments in deployment manager
0. Bind Deployment Manager Editor role to your Google account
0. Replace DEPL_NAME with a deployment name, FILENAME with each *.yaml files, then execute the command 
```shell script
gcloud config  set project PROJECT_ID
gcloud deployment-manager deployments create DEPL_NAME --config infra/FILENAME.yaml
```
0. Inspect [the deployment's result](https://console.cloud.google.com/dm/deployments)

### Set up the local development environment

0. Generate a JSON key file for the service account the infra/svc*.yaml deployment created.
0. set GOOGLE_APPLICATION_CREDENTIALS environment variable to that key file's path.
0. set MON_GCP_PROJECT environment variable to the Google cloud Project ID that has the monitoring workspaces
0. set PORT environment variable for the Python flask application.
0. Examine unittests.py's first few lines to set required environment variables

### Prerequisites such as Python >= 3.8

requirements.txt shows required Python modules for the app to
run. Example python development environment creation steps:

```shell script
$ python3 -m venv .
$ . bin/python
$ python --version # verify the python version
$ pip install -r requirements.txt
```
If PORT environment variable is not set, app will run on 8080. Make sure
the port is free to use. The main module is gke_cpu.py which you should select in Pycharm's debug configuration.

### Basic testing
```shell
$ time curl 'http://localhost:8080/projects/some*project*glob/start-datetime/2020-10-24_00:00:00/end-datetime/2020-10-25_00:00:00/alignment_period_seconds/3600'
```

## License

This project is licensed under [Apache License, Version 2.0 (Apache 2.0)](http://www.apache.org/licenses/LICENSE-2.0)
