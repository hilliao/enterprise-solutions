# Foodstore customer order management

A simple food order management application for restaurant food suppliers
to manage orders from restaurants. A typical workflow is the sysadmin
provisions a restaurant as a customer entity -> customer entity has a
document ID -> restaurant puts the document ID in the header to place
and manage orders.

## Getting Started

Build, Develop, Test, Deploy the project from localhost to Google Cloud
Platform. Python and Angular skills are required.

### Prerequisites

0. Python >= 3.7
0. Docker >= 18.09.2
0. Postman >= 6.7.1
0. Pycharm >= 2018.3

### Installing

0. Create a virtual environment for development 

```
$ virtualenv --python=/usr/bin/python3.7 foodstore
```
1. upon success, open Pycharm and configure project interpreter to foodstore/bin/python.
2. Create a service account with predefined role of Cloud Datastore
   User. Download the .json account key file to $HOME/secrets.
3. Right click on the line of *app.run* in foodstore/api.py and select
   Debug 'api'
3. Set the Run/Debug configurations to have environment variables of
   GOOGLE_APPLICATION_CREDENTIALS=**$HOME/secrets/key.json**,
   GCLOUD_PROJECT=**Project ID**


## Running the tests

0. Install the latest Postman and import test/*postman*.json files where 1 is the environment and the other is the collection of tests
1. Start debugging the api flask application in Pycharm at port 5000. In
   Postman, Select the localhost environment and choose get orders
2. Set header customer_token to be the Document ID of a customer; set in
   URL /orders/{order ID} to get the order, hit send.

## Deployment

Build and run a local Docker container to test before deploying to
Google Cloud Platform
```
$ cd foodstore/backend
$ docker build -t foodstore:test .
$ docker run -d -e "PORT=5000" -p 500:5000 -v $HOME/secrets:/secrets -e "GOOGLE_APPLICATION_CREDENTIALS=/secrets/**key.json**" -e "GCLOUD_PROJECT=**ProjectID**"  foodstore:test
```
Change Postman's environment to docker and run the same get orders
request. Upon success, follow [Cloud build and
deploy](https://cloud.google.com/run/docs/quickstarts/build-and-deploy)
to deploy to managed Cloud Run.