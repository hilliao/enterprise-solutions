play with http verbs on Google cloud Platform with Datastore
==================

the application follows a similar structure to https://cloud.google.com/appengine/docs/java/endpoints/helloendpoints-java-maven

Change the value of hil-micro-use</application> in appengine-web.xml: set to project ID in Google cloud platform

Build run, and deploy in Google cloud SDK shell

Set your project-ID: gcloud config set project hil-micro-use

To build: mvn clean install

To run locally: mvn appengine:devserver

To deploy: mvn appengine:update