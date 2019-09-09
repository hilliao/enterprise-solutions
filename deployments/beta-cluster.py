# Copyright 2016 TechSightTeam Inc. All rights reserved.
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
#
# Google Cloud deployment manager python template for creating a Kubernetes Engine with beta features


def GenerateConfig(context):
    '''Generate YAML resource configuration.'''

    name_prefix = context.env['deployment'] + '-' + context.env['name']
    cluster_name = name_prefix
    k8s_endpoints = {
        '': 'api/v1',
        '-apps': 'apis/apps/v1beta1',
        '-v1beta1-extensions': 'apis/extensions/v1beta1'
    }

    resources = [
        {
            'name': cluster_name,
            'type': 'gcp-types/container-v1beta1:projects.locations.clusters',
            'properties': {
                'parent': 'projects/{}/locations/{}'.format(context.env['project'], context.properties['region']),

                'cluster': {
                    'name': cluster_name,
                    'masterAuth': {
                        'clientCertificateConfig': {}
                    },
                    'loggingService': 'logging.googleapis.com/kubernetes',
                    'monitoringService': 'monitoring.googleapis.com/kubernetes',
                    'network': 'projects/hilliao-on-justinburke/global/networks/default',
                    'addonsConfig': {
                        'httpLoadBalancing': {},
                        'horizontalPodAutoscaling': {},
                        'kubernetesDashboard': {
                            'disabled': True
                        },
                        'istioConfig': {},
                        'cloudRunConfig': {}
                    },
                    'subnetwork': 'projects/hilliao-on-justinburke/regions/us-west1/subnetworks/default',
                    'nodePools': [
                        {
                            'name': 'default-pool',
                            'config': {
                                'machineType': 'n1-standard-1',
                                'diskSizeGb': 10,
                                'oauthScopes': [
                                    'https://www.googleapis.com/auth/devstorage.read_only',
                                    'https://www.googleapis.com/auth/logging.write',
                                    'https://www.googleapis.com/auth/monitoring',
                                    'https://www.googleapis.com/auth/servicecontrol',
                                    'https://www.googleapis.com/auth/service.management.readonly',
                                    'https://www.googleapis.com/auth/trace.append'
                                ],
                                'metadata': {
                                    'disable-legacy-endpoints': 'true'
                                },
                                'imageType': 'COS',
                                'preemptible': True,
                                'diskType': 'pd-ssd',
                                'shieldedInstanceConfig': {
                                    'enableSecureBoot': True,
                                    'enableIntegrityMonitoring': True
                                }
                            },
                            'initialNodeCount': 1,
                            'autoscaling': {
                                'enabled': True,
                                'minNodeCount': 1,
                                'maxNodeCount': 3
                            },
                            'management': {
                                'autoUpgrade': True,
                                'autoRepair': True
                            },
                            'version': '1.13.7-gke.24'
                        }
                    ],
                    'networkPolicy': {},
                    'ipAllocationPolicy': {
                        'useIpAliases': True
                    },
                    'masterAuthorizedNetworksConfig': {},
                    'binaryAuthorization': {
                        'enabled': True
                    },
                    'defaultMaxPodsConstraint': {
                        'maxPodsPerNode': '110'
                    },
                    'authenticatorGroupsConfig': {
                        'enabled': True,
                        'securityGroup': 'gke-security-groups@tributetea.com'
                    },
                    'privateClusterConfig': {},
                    'databaseEncryption': {
                        'state': 'DECRYPTED'
                    },
                    'verticalPodAutoscaling': {
                        'enabled': True
                    },
                    'initialClusterVersion': '1.13.7-gke.24',
                    'location': 'us-west1'
                }
            }
        }
    ]

    return {'resources': resources}
