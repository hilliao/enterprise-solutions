import datetime
import pytz
import googleapiclient.discovery
import os

# 2019-11-22 13:38:19.581781
METADATA_EXPIRY = 'expiry'
METADATA_EXPIRY_1 = 'expiry-1'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'

# expiry metadata datetime assumes to be the following timezone
ASSUMED_TIME_ZONE = 'America/Los_Angeles'

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
                if metadata['key'] == METADATA_EXPIRY:
                    expiry = datetime.datetime.strptime(metadata['value'], DATETIME_FORMAT)
                    delete_expired_instance(expiry, instance, project, zone)

                # workbench UI accepts date - 1, add 1 day to the parsed date
                if metadata['key'] == METADATA_EXPIRY_1:
                    expiry_1 = datetime.datetime.strptime(metadata['value'], '%Y-%m-%d')
                    expiry = expiry_1 + datetime.timedelta(days=1)
                    delete_expired_instance(expiry, instance, project, zone)


def delete_expired_instance(expiry, instance, project, zone):
    print('    parsed expiry in PST: ' + str(expiry))
    timezone = pytz.timezone(ASSUMED_TIME_ZONE)
    expiry_tz = timezone.localize(expiry)
    if expiry_tz < datetime.datetime.now(timezone):
        print('    WARNING! about to delete instance ' + instance['name'])
        delete_op = delete_instance(compute, project, zone, instance['name'])
        print('    deleting instance operation: ' + delete_op['name'])


def main(event, context):
    project = os.environ['GCLOUD_PROJECT']
    result = compute.zones().list(project=project).execute()
    for zone in result['items']:
        delete_expired(project, zone['name'])
