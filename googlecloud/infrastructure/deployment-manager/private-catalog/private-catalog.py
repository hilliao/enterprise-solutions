# Copyright 2021 GoogleCloud.fr; All rights reserved.
#
# Create a deployment manager action which execute cloud build steps as a 1 time task
# Expect the deployment to have a warning sign in the deployment manager page as action is not obsolete
# Summary of the build steps:
#   clone a public git repository
#   create a new cloud source repository
#   create a cloud build trigger referencing it

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
                        f'apt-get update && apt-get -y install gettext-base && '
                        f'git clone https://github.com/hilliao/enterprise-solutions.git && '
                        f'gcloud source repos create {repo} --project {project_id} && '
                        f'cd enterprise-solutions && '
                        f'git config --global credential.https://source.developers.google.com.helper gcloud.sh && '
                        f'git remote add google https://source.developers.google.com/p/{project_id}/r/{repo} && '
                        f'git push --all google && '
                        f'export CSR_REPO={repo} && export CSR_REPO_PATH=$$REPO_PATH && export BUILD_PROJECT_ID={project_id} && export TRIGGER_NAME={build_trigger} && '
                        f"envsubst '$$CSR_REPO,$$CSR_REPO_PATH,$$BUILD_PROJECT_ID,$$TRIGGER_NAME' < $$CSR_REPO_PATH/build-triggers-gke.sh > /workspace/build-triggers-gke.sh && "
                        f"echo executing the following BASH script... && cat /workspace/build-triggers-gke.sh && sh /workspace/build-triggers-gke.sh"

                    ],
                    'env': [
                        'PRODUCTION=false',
                        'REPO_PATH=googlecloud/infrastructure/blueprints'
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
