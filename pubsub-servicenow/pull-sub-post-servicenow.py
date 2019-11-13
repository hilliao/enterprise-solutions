# Need to install requests package for python3
import requests
import os
import json
from google.cloud import pubsub_v1

user = 'admin'
pwd = os.environ['admin_password']
subscription_name = os.environ['SUBSCRIPTION_NAME']
subscriber = pubsub_v1.SubscriberClient()
servicenow_instance_url = 'https://dev88732.service-now.com/api/now/table/incident'


def servicenow_create_incident(url, description, comments):
    # Servicenow instance URL
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    requestbody = {
        "short_description": description,
        "comments": comments
    }

    # Post the HTTP request
    response = requests.post(url, auth=(user, pwd), headers=headers, json=requestbody)
    print('Status:', response.status_code, 'Headers:', response.headers)
    return response.json()


def callback(message):
    print('Received message: {}'.format(message))
    print('Received message data: {}'.format(message.data))
    msg = json.loads(message.data)
    if msg['severity'] == "ERROR":
        # log incident for errors
        try:
            incident = servicenow_create_incident(url=servicenow_instance_url, description=str(msg),
                                                  comments=msg['insertId'])
        except Exception as e:
            print('servicenow incident create REST API failed: {}'.format(e))
        print('incident {} created:'.format(incident['result']['sys_id']))
    if message.attributes:
        print('Attributes:')
        for key in message.attributes:
            value = message.attributes.get(key)
            print('{}: {}'.format(key, value))
    message.ack()


def pull_sub_til_ex():
    future = subscriber.subscribe(subscription_name, callback=callback)
    try:
        # parameter is timeout in seconds. Not passing it means method waits indefinitely
        future.result()
    except Exception as e:
        # exception exists the waiting state. put the method in an infinite loop to keep pulling
        print('Listening for messages on {} threw an Exception: {}.'.format(subscription_name, e))


# run the pull subscription asynchronously and print any exceptions in an infinite loop
while (True):
    pull_sub_til_ex()
