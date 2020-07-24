# Google AI platform notebook instance management solution

A microservice deployed in Google Cloud Run that manages Google cloud AI platform notebook
instances

## Getting Started

### Set up the local development environment

Intellij should recognize the directory as a gradle project. Set Java version 
0. Settings > Build, Execution, Deployment > Build TOols > Gradle > Gradel JVM to Java 11
0. Settings > Build, Execution, Deployment > Compiler > Java Compiler > Project bytecode version to 11

If no error occurs, the Run/Debug configurations  on the menu  should show you a debug button.
Click the run or debug button to start the spring boot application.

### Prerequisites

0. Intellij needs to be greater than or equal to  2020.1
0. Intellij has Java 11 installed
0. The Google account user has AI Platform notebook admin role
0. The service account for Cloud Run needs the following predefined roles for Cloud debug, trace to function.
The other predefined roles recommended:
- Cloud Debugger Agent
- Cloud Trace Agent
- Errors Writer
- Logs Writer

### Installing
Clone the code to your cloud source repository. With Cloud build trigger
configured, pushing to the cloud source repository will trigger the
build and deployment to Cloud Run. Verify Cloud Run is enabled in your
project. Change the following section in cloudbuild.yaml
for Cloud run related customization.

```
- name: 'gcr.io/cloud-builders/gcloud'
  args: ['run', 'deploy'
```

## Running the tests
Call the /sleep?seconds=0 endpoint to see if 200 is returned
```
curl localhost:8080/sleep?seconds=0
curl https://$CLOUD_RUN_URL/sleep?seconds=0 -k
```

### Break down into end to end tests

use the following JSON request body 
```

curl --request POST \
  --url http://localhost:8080/createAINotebook \
  --header "authorization: $(gcloud auth print-access-token)" \
  --header 'content-type: application/json' \
  --data '{
          	"projectId"	: "project ID to create the AI platform notebooks in",
          	"instanceName":"my-ai-notebook-0",
          	"VPCProjectId":"The shared VPC host project ID",
          	"VPCName":"Shared VPC name or default",
          	"subnetName":"subnet in the VPC such as default",
          	"region":"Google cloud region",
          	"zone":"Google cloud zone"
          }'
```

## Deployment

Inspect the Cloud trace, Cloud Debugger, Cloud Logging to see invoking
the endpoints create the trace, logs, and an active debugging
application. the latency for the trace or logs to show is usually 2
minutes; setting a snapshot in the Cloud Debugger and hitting the
endpoint may not catch a snapshot right away. Maybe there was some lag.
It's usually the 2nd time of hitting the endpoint to catch the snapshot.

## License

This project is licensed under the MIT License