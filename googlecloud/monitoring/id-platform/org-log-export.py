# Copyright 2021 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Bind Pub/Sub Admin role to the deployment manager service account $PROJECT_NUMBER@cloudservices.gserviceaccount.com in the project
# Bind Logging Admin role to the deployment manager service account $PROJECT_NUMBER@cloudservices.gserviceaccount.com at the organization level

ORGANIZATIONS = 'organizations'


def create_topic(topic_name, sink_name):
    """ Create a Pub/Sub topic.

    Keyword arguments:
    topic_name -- pub/sub Topic Name.
    sink_name  -- logs router Sink resource has a .writerIdentity output
    """
    topic = {
        'name': f"topic-{topic_name}",
        'type': 'pubsub.v1.topic',
        'properties': {
            'topic': topic_name
        },
        'accessControl': {
            'gcpIamPolicy': {
                'bindings': {
                    'role': 'roles/pubsub.publisher',
                    # logs router sink creates a Google service account as writerIdentity
                    'members': [f"$(ref.{sink_name}.writerIdentity)"]
                }
            }
        }
    }

    return topic


def create_subscription(subscription_name, topic_name):
    """ Create a Pub/Sub Pull Subscription.

    Keyword arguments:
    subscription_name -- The name for the new Subscription.
    topic_name        -- The topic name where the subscription is created.
    """

    subscription = {
        'name': f"sub-{subscription_name}",
        'type': 'pubsub.v1.subscription',
        'properties': {
            'subscription': subscription_name,
            'topic': f"$(ref.topic-{topic_name}.name)"
        }
    }

    return subscription


def create_sink(org_id, sink_name, sink_filters, destination):
    """ Create a Logs router Sink to export logs to a given Pub/Sub topic.

    Keyword arguments:
    org_id       --  Google cloud Organization ID as an integer.
    sink_name    --  The name for the new logs router Sink.
    sink_filters --  The log filter options for the new logs router sink.
    destination  --  The destination where the sink is going to export the logs such as a pub/sub topic

    """
    properties = {'name': sink_name, 'uniqueWriterIdentity': True, 'sink': sink_name,
                  'parent': f"{ORGANIZATIONS}/{org_id}", 'destination': destination,
                  'filter': sink_filters,
                  'organization': org_id}

    resource = {
        'name': f"sink-{sink_name}",
        'type': 'gcp-types/logging-v2:{}.sinks'.format(ORGANIZATIONS),
        'properties': properties
    }

    return resource


def generate_filters(org_id):
    """ Generate Log Filters on organizations/$ORGANIZATION_ID

    Keyword arguments:
    org_id -- Google cloud organization ID as an integer
    """
    filters = ['"{}/{}/logs/cloudaudit.googleapis.com%2Factivity"'.format(ORGANIZATIONS, org_id),
               '"{}/{}/logs/cloudaudit.googleapis.com%2Fdata_access"'.format(ORGANIZATIONS, org_id)]
    filters_str = " OR ".join(filters)

    return f"logName=({filters_str})"


def display_outputs(sink_name):
    """ display the deployment outputs in the deployment manager console page > layout

    Keyword arguments:
    sink_name       -- Logs router Sink Resource name to show the .writerIdentity output
    """
    return [
        {
            'name': 'sink-writerIdentity',
            'value': '$(ref.' + sink_name + '.writerIdentity)'
        }
    ]


def generate_config(context):
    """ Entry point for the deployment resources. """

    # Context Variables.
    resource_name = context.env['name']
    project_id = context.env['project']
    org_id = context.properties.get('org_id')

    # generate a string put in the logging page to filter logs
    sink_filters = generate_filters(org_id)

    # if not passed, create a new topic
    topic_id = context.properties.get('use_existing_topic', "")

    # Setting the Resource Names to avoid naming conflicts
    topic_name = resource_name
    subscription_name = resource_name
    sink_name = resource_name

    resource_list = []

    if not topic_id:
        # the topic depends on the logs router sink's .writerIdentity causing the logs router sink to be created first
        # create a pub/sub Topic, subscription
        topic_resource = create_topic(topic_name, f"sink-{sink_name}")
        subscription_resource = create_subscription(subscription_name, topic_name)
        topic_id = f"pubsub.googleapis.com/projects/{project_id}/topics/{topic_name}"

        resource_list.extend([topic_resource, subscription_resource])

    # Create a logs router sink to export logs for the topic
    sink_resource = create_sink(org_id, sink_name, sink_filters, topic_id)
    resource_list.append(sink_resource)

    return {
        'resources': resource_list,
        'outputs': display_outputs(f"sink-{sink_name}")
    }
