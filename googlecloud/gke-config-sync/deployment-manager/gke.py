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

def GenerateConfig(context):
    # type from https://cloud.google.com/deployment-manager/docs/configuration/supported-resource-types

    gke_name = context.properties['gke-name']
    zone = context.properties['zone']
    region = context.properties['region']
    vpc = context.properties['vpc']
    subnet = context.properties['subnet']
    clusterIpv4CidrBlock = context.properties['clusterIpv4CidrBlock']
    servicesIpv4CidrBlock = context.properties['servicesIpv4CidrBlock']
    masterIpv4CidrBlock = context.properties['masterIpv4CidrBlock']

    resources = [
        {
            'name': gke_name,
            'type': 'container.v1.cluster',
            'properties':
                {
                    "zone": zone,
                    "cluster": {
                        "name": gke_name,
                        "masterAuth": {
                            "clientCertificateConfig": {}
                        },
                        "network": f"projects/{context.env['project']}/global/networks/{vpc}",
                        "addonsConfig": {
                            "httpLoadBalancing": {},
                            "horizontalPodAutoscaling": {},
                            "kubernetesDashboard": {
                                "disabled": True
                            },
                            "networkPolicyConfig": {},
                            "dnsCacheConfig": {},
                            "gcePersistentDiskCsiDriverConfig": {
                                "enabled": True
                            }
                        },
                        "subnetwork": f"projects/{context.env['project']}/regions/{region}/subnetworks/{subnet}",
                        "nodePools": [
                            {
                                "name": "default-pool",
                                "config": {
                                    "machineType": "e2-medium",
                                    "diskSizeGb": 30,
                                    "oauthScopes": [
                                        "https://www.googleapis.com/auth/cloud-platform"
                                    ],
                                    "metadata": {
                                        "disable-legacy-endpoints": "true"
                                    },
                                    "imageType": "COS",
                                    "tags": [
                                        "gke-egress-all"
                                    ],
                                    "preemptible": True,
                                    "diskType": "pd-ssd",
                                    "shieldedInstanceConfig": {
                                        "enableIntegrityMonitoring": True
                                    }
                                },
                                "initialNodeCount": 1,
                                "autoscaling": {
                                    "enabled": True,
                                    "maxNodeCount": 2
                                },
                                "management": {
                                    "autoUpgrade": True,
                                    "autoRepair": True
                                },
                                "maxPodsConstraint": {
                                    "maxPodsPerNode": "110"
                                },
                                "upgradeSettings": {
                                    "maxSurge": 1
                                }
                            },
                        ],
                        "locations": [
                            zone
                        ],
                        "resourceLabels": {
                            "use": "deployment-manager-test-0"
                        },
                        # "networkPolicy": {
                        #     "provider": "CALICO",
                        #     "enabled": True
                        # },
                        "ipAllocationPolicy": {
                            "useIpAliases": True,
                            "clusterIpv4CidrBlock": clusterIpv4CidrBlock,
                            "servicesIpv4CidrBlock": servicesIpv4CidrBlock
                        },
                        "masterAuthorizedNetworksConfig": {},
                        "binaryAuthorization": {
                            "enabled": True
                        },
                        "autoscaling": {},
                        "defaultMaxPodsConstraint": {
                            "maxPodsPerNode": "110"
                        },
                        "authenticatorGroupsConfig": {},
                        "privateClusterConfig": {
                            "enablePrivateNodes": True,
                            "masterIpv4CidrBlock": masterIpv4CidrBlock,
                            "masterGlobalAccessConfig": {
                                "enabled": True
                            }
                        },
                        "databaseEncryption": {
                            "state": "DECRYPTED"
                        },
                        "shieldedNodes": {
                            "enabled": True
                        },
                        "releaseChannel": {
                            "channel": "REGULAR"
                        },
                        "workloadIdentityConfig": {
                            "workloadPool": f"{context.env['project']}.svc.id.goog"
                        },
                        "notificationConfig": {
                            "pubsub": {}
                        },
                        "initialClusterVersion": "1.18.15-gke.1501",
                        "location": zone
                    }
                }
        }
    ]

    return {'resources': resources}
