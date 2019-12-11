#!/usr/bin/env python

# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Example of deleting instances of expiry custom metadata and instance group
For more information, see the README.md
"""

import datetime
import pytz
import googleapiclient.discovery
import os

# 2019-11-22 13:38:19.581781
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
# 2019-11-22
DATE_FORMAT = '%Y-%m-%d'
METADATA_EXPIRY = 'expiry'
METADATA_EXPIRY_1 = 'expiry-1'
METADATA_WORKER_GROUP = 'worker-group'

# expiry metadata datetime assumes to be the following timezone
ASSUMED_TIME_ZONE = 'America/Los_Angeles'
all_zones = []
compute = googleapiclient.discovery.build('compute', 'v1')


def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None


# [START delete_instance]
def delete_instance(compute, project, zone, name):
    return compute.instances().delete(
        project=project,
        zone=zone,
        instance=name).execute()


# [END delete_instance]


def delete_expired(project, zone):
    """
    Delete expired compute engine instances with worker group metadata set to an instance group to delete
    :param project: Google Cloud project ID
    :param zone: compute engine zone
    :return: None TODO: change to return the delete operation
    """
    instances = list_instances(compute, project, zone)
    if not instances:
        print('no instances in project %s and zone %s to delete' % (project, zone))
        return
    print('searching for expired instances in project %s and zone %s:' % (project, zone))

    for instance in instances:
        print('  inspecting instance {} metadata'.format(instance['name']))

        # if no custom metadata set, continue to the next instance
        if 'items' in instance['metadata']:
            metadata_items = instance['metadata']['items']

            for metadata in metadata_items:
                expiry = None

                if metadata['key'] == METADATA_EXPIRY:
                    expiry = datetime.datetime.strptime(metadata['value'], DATETIME_FORMAT)

                # workbench UI accepts date - 1, add 1 day to the parsed date
                if metadata['key'] == METADATA_EXPIRY_1:
                    expiry_1 = datetime.datetime.strptime(metadata['value'], DATE_FORMAT)
                    expiry = expiry_1 + datetime.timedelta(days=1)

                # delete the instance group and instances only when expiry is in metadata
                if expiry:
                    groups = [metadata['value'] for metadata in metadata_items
                              if metadata['key'] == METADATA_WORKER_GROUP]
                    delete_expired_instance(expiry, instance, project, zone, groups)


def delete_instance_group(group, project, zone):
    """
    delete the instance group in the Google cloud project and zone's region. Caution: does not delete regional instance
    group ref: https://cloud.google.com/compute/docs/reference/rest/v1/regionInstanceGroupManagers/delete
    :param group: the instance group name
    :param project: Google cloud project ID
    :param zone: Multiple zones in the zone's region would be inspected for instance group deletion
    :return: None TODO: change to return the delete operation delete_op
    """
    print('    WARNING! about to delete instance group: ' + group)
    # assume the worker instance group is in the same region of the zone argument
    zones = [z for z in all_zones if z.startswith(zone[:-1])]
    for z in zones:
        try:
            delete_op = compute.instanceGroupManagers().delete(
                project=project,
                zone=z,
                instanceGroupManager=group).execute()
            print('    deleting instance group operation: ' + delete_op['name'])
        except googleapiclient.errors.HttpError as err:
            print('    deleting instance group {} in zone {} failed: {}'.format(group, z, err))


def delete_expired_instance(expiry, instance, project, zone, groups):
    """
    given the project, zone, and instance group name, delete expired instance and referenced instance group in the
     zone's region. If the expiry is in the future, no deletion of instance or instance groups occur
    :param expiry: if the current datetime is greater than expiry in assumed time zone, proceed with deletion
    :param instance: the compute engine instance name to be deleted
    :param project: the Google cloud project ID
    :param zone: the zone parameter to pass to the compute engine API
    :param groups: the instance group name
    :return: None TODO: change to return the delete operation delete_op
    """
    print('    parsed expiry in PST: ' + str(expiry))
    timezone = pytz.timezone(ASSUMED_TIME_ZONE)
    expiry_tz = timezone.localize(expiry)

    if expiry_tz < datetime.datetime.now(timezone):
        # delete the instance group first; instances in an instance group can't be deleted
        if groups:
            for group in groups:
                delete_instance_group(group, project, zone)

        print('    WARNING! about to delete instance: ' + instance['name'])
        delete_op = delete_instance(compute, project, zone, instance['name'])
        print('    deleting instance operation: ' + delete_op['name'])


# for Google cloud function --entry-point=main
def main(event, context):
    global all_zones
    project = os.environ['GCP_PROJECT']
    listing_zones_result = compute.zones().list(project=project).execute()
    all_zones = [zone['name'] for zone in listing_zones_result['items']]

    for zone in all_zones:
        delete_expired(project, zone)


# for local debugging in Pycharm
if __name__ == "__main__":
    main(None, None)
