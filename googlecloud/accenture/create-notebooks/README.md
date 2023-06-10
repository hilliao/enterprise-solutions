# Create Google AI platform notebooks via Google REST API

A microservice deployed in Google Cloud Run to create Google cloud AI platform notebook instances. There was no official
documentation on any client library to create AI platform notebooks. I discovered the Google REST API by debugging on
Google cloud coole AI platform notebook page during manual notebook creation. The result is similar to creating with
gcloud command:
```shell script
OWNER=your_name
PROJECT_ID=
INSTANCE_NAME=
GCP_SA=
VPC_HOST_PROJ=
VPC_NET=
SUBNET=
REGION=us-east1
ZONE=us-east1-b

gcloud beta notebooks instances create $INSTANCE_NAME --location=$ZONE --vm-image-family=tf2-2-3-cu110-notebooks-debian-10 \
--vm-image-project=deeplearning-platform-release --machine-type=e2-standard-2 --labels=owner=$OWNER \
--metadata=framework=TensorFlow:2.3 --service-account=$GCP_SA \
--network=projects/$VPC_HOST_PROJ/global/networks/$VPC_NET \
--subnet=projects/$VPC_HOST_PROJ/regions/$REGION/subnetworks/$SUBNET  --no-public-ip \
--project $PROJECT_ID
``` 

## Getting Started

### Set up the local development environment

Intellij should recognize the directory as a gradle project. Set Java version
 
0. Settings > Build, Execution, Deployment > Build Tools > Gradle > Gradle JVM to Java 11
0. Settings > Build, Execution, Deployment > Compiler > Java Compiler > Project bytecode version to 11

If no error occurs, the Run/Debug configurations  on the menu  should show you a debug button. If none shows, create a
Spring Boot application in Run/Debug configurations.
Click the run or debug button to start the spring boot application.

### Prerequisites

0. Intellij needs to be greater than or equal to  2020.1
0. Intellij has Java 11 installed
0. The Google account user has AI Platform notebook admin role
0. The service account in the deployed Cloud Run service or in Intellij debug configuration's
 GOOGLE_APPLICATION_CREDENTIALS environment variable needs the following predefined roles for Cloud debug, logging,
  trace to function.
    - Cloud Debugger Agent
    - Cloud Trace Agent
    - Errors Writer
    - Logs Writer

### Installing
Clone the code to your cloud source repository. With Cloud build trigger
configured, pushing to the cloud source repository will trigger the
build and deployment to Cloud Run. Verify Cloud Run is enabled in your
project.

Add [--service-account parameter](https://cloud.google.com/sdk/gcloud/reference/run/deploy#--service-account) to 
`gcloud run deploy` and specify a Google service account with recommended roles in cloudbuild.yaml. Otherwise,
compute engine default service account will be used.
 For Cloud run related customization, substitute $_SVC_NAME with the Cloud run service name in build trigger.
 
## Running the basic tests
Call the /sleep?seconds=0 endpoint to see if 200 is returned
```
curl localhost:8080/sleep?seconds=0
curl https://$CLOUD_RUN_URL/sleep?seconds=0 -k
```

## Post Deployment Tests 

Import the postman collection at the upper directory to call the REST API. The Authorization header does not have
`Bearer`

To use a Debian 10 image family, append `-notebooks-debian-10` to a value in
 [imageFamily](https://cloud.google.com/ai-platform/deep-learning-vm/docs/images). 
For example, tf2-2-3-cu110-notebooks-debian-10

Inspect the Cloud trace, Cloud Debugger, Cloud Logging to see invoking
the endpoints create the trace, logs, and an active debugging
application. the latency for the trace or logs to show is usually 2
minutes; setting a snapshot in the Cloud Debugger and hitting the
endpoint may not catch a snapshot right away. Maybe there was some lag.
It's usually the 2nd time of hitting the endpoint to catch the snapshot.

## License

This project is licensed under [Apache License, Version 2.0 (Apache 2.0)](http://www.apache.org/licenses/LICENSE-2.0)

## Known issues
The following trace annotation does not seem to have effects
```java
        tracer.getCurrentSpan().addAnnotation("Calling " + url);
```