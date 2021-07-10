# Copyright 2021 GoogleCloud.fr; All rights reserved.
#
# Create a deployment manager action which execute a cloud build as a 1 time task
# Expect the deployment to have a warning sign in the deployment manager page as action is not obsolete

def GenerateConfig(context):
    build_name = 'gcloud-exec'
    project_id = context.properties['PROJECT_ID']
    repo = context.properties['REPO']
    build_trigger = context.properties['BUILD_TRIGGER']

    resources = [{
        'name': build_name,
        'action': 'gcp-types/cloudbuild-v1:cloudbuild.projects.builds.create',
        'metadata': {
            'runtimePolicy': ['CREATE'],
        },
        'properties': {
            'steps': [
                {
                    'name': 'gcr.io/google.com/cloudsdktool/cloud-sdk:latest',
                    'entrypoint': 'bash',
                    'args': [
                        '-c',
                        f'echo is production? $$PRODUCTION && '
                        f'git clone https://github.com/hilliao/enterprise-solutions.git && '
                        f'gcloud source repos create {repo} --project {project_id} && '
                        f'cd enterprise-solutions && '
                        f'git config --global credential.https://source.developers.google.com.helper gcloud.sh && '
                        f'git remote add google https://source.developers.google.com/p/{project_id}/r/{repo} && '
                        f'git push --all google && '
                        f'gcloud beta builds triggers create cloud-source-repositories \
                            --repo={repo} --name={build_trigger} \
                            --branch-pattern="^master$" \
                            --build-config="$$REPO_PATH/cloudbuild-gke.yaml" \
                            --included-files="$$REPO_PATH/**" \
                            --ignored-files="**/README.md" \
                            --substitutions _GKE_CLUSTER_NAME=hil-blueprints-test,_DEPLOYMENT_NAME=hil-blueprints-test,_GKE_REGION=us-west1,_VPC=default,_SUBNET=default,_POD_IP_RANGE_NAME=gke-hil-pods,_SVC_IP_RANGE_NAME=gke-hil-services,_MASTER_IP_RANGE=172.22.32.0/28,_BLUEPRINTS_DIR=$$REPO_PATH,_MACHINE_TYPE=e2-medium,_IF_PREEMPTIBLE=true,_DISK_GB=55 \
                            --project {project_id}'

                    ],
                    'env': [
                        'PRODUCTION=false',
                        'REPO_PATH=googlecloud/gke-config-sync/blueprints'
                    ]
                }
            ],
            'timeout': '1200s'
        }
    }]

    outputs = [
        {
            'name': "id",
            'value': f"$(ref.{build_name}.id)"
        },
        {
            'name': "status",
            'value': f"$(ref.{build_name}.status)"
        }
    ]

    return {
        'resources': resources, 'outputs': outputs
    }
