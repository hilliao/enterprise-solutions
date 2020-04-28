"""Enable Google Cloud APIs"""


def GenerateConfig(context):
    project_id = context.env['project']
    service_account = context.properties['service-account']

    resources = [{
        'name': context.env['name'] + '-enable-apis',
        'type': 'deploymentmanager.v2.virtual.enableService',
        'properties': {
            'consumerId': 'project:' + project_id,
            'serviceName': context.properties['svc_googleapis_com'] + '.googleapis.com'  # bigquery.googleapis.com
        }
    },
        {
            'name': context.env['name'] + '-service-account',
            'type': 'iam.v1.serviceAccount',
            'properties': {
                'accountId': service_account,
                'displayName': service_account,
                'projectId': project_id
            }
        },
        {
            'name': context.env['name'] + '-bind-iam-policy',
            'type': 'gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding',
            'properties': {
                'resource': project_id,
                'role': context.properties['role'],  # 'roles/dataflow.admin',
                'member': 'serviceAccount:$(ref.' + context.env['name'] + '-service-account' + '.email)'
            },
            'metadata': {
                'dependsOn': [context.env['name'] + '-service-account']
            }
        }
    ]

    return {'resources': resources}
