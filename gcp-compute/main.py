import datetime
import pytz
import googleapiclient.discovery
import os

# 2019-11-22 13:38:19.581781
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
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
                    delete_expired_instances(expiry, instance, project, zone, groups)


def delete_worker_group(group, project, zone):
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


def delete_expired_instances(expiry, instance, project, zone, groups):
    print('    parsed expiry in PST: ' + str(expiry))
    timezone = pytz.timezone(ASSUMED_TIME_ZONE)
    expiry_tz = timezone.localize(expiry)

    if expiry_tz < datetime.datetime.now(timezone):
        # delete the instance group first; instances in an instance group can't be deleted
        if groups:
            for group in groups:
                delete_worker_group(group, project, zone)

        print('    WARNING! about to delete instance: ' + instance['name'])
        delete_op = delete_instance(compute, project, zone, instance['name'])
        print('    deleting instance operation: ' + delete_op['name'])


def main(event, context):
    global all_zones
    project = os.environ['GCP_PROJECT']
    listing_zones_result = compute.zones().list(project=project).execute()
    all_zones = [zone['name'] for zone in listing_zones_result['items']]

    for zone in all_zones:
        delete_expired(project, zone)


if __name__ == "__main__":
    main(None, None)
