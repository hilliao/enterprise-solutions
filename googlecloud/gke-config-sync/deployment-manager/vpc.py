"""
Create a VPC network and its firewall rules. Notice the self link in firewall rules:
    "$(ref.{network_name}.selfLink)"
The selfLink is critical for deployment manager to recognize the dependency and create the resources in the correct
order per https://cloud.google.com/deployment-manager/docs/configuration/use-references
"""

def GenerateConfig(context):
    network_name = context.properties['vpc-name']
    desc = context.properties['vpc-desc']

    # type from https://cloud.google.com/deployment-manager/docs/configuration/supported-resource-types
    resources = [
        {
            'name': network_name,
            'type': 'compute.v1.network',
            'properties': {
                "autoCreateSubnetworks": True,
                "description": desc,
                "mtu": 1460,
                "name": network_name,
                "routingConfig": {
                    "routingMode": "GLOBAL"
                }
            }
        },
        {
            "type": "compute.v1.firewall",
            "name": network_name + "-allow-icmp",
            'properties': {
                # https://cloud.google.com/deployment-manager/docs/configuration/templates/use-environment-variables
                "project": context.env['project'],
                "allowed": [
                    {
                        "IPProtocol": "icmp"
                    }
                ],
                "description": "Allows ICMP connections from any source to any instance on the network.",
                "direction": "INGRESS",
                "network": f"$(ref.{network_name}.selfLink)",
                "priority": 65534,
                "sourceRanges": [
                    "0.0.0.0/1"
                ]
            }
        },
        {
            "type": "compute.v1.firewall",
            "name": network_name + "-allow-internal",
            'properties': {
                "project": context.env['project'],
                "allowed": [
                    {
                        "IPProtocol": "all"
                    }
                ],
                "description": "Allows connections from any source in the network IP range to any instance on the network using all protocols.",
                "direction": "INGRESS",
                "network": f"$(ref.{network_name}.selfLink)",
                "priority": 65534,
                "sourceRanges": [
                    "10.128.0.0/9"
                ]
            }
        },
        {
            "type": "compute.v1.firewall",
            "name": network_name + "-allow-rdp",
            'properties': {
                "project": context.env['project'],
                "allowed": [
                    {
                        "IPProtocol": "tcp",
                        "ports": [
                            "3389"
                        ]
                    }
                ],
                "description": "Allows RDP connections from any source to any instance on the network using port 3389.",
                "direction": "INGRESS",
                "network": f"$(ref.{network_name}.selfLink)",
                "priority": 65534,
                "sourceRanges": [
                    "0.0.0.0/1"
                ]
            }
        },
        {
            "type": "compute.v1.firewall",
            "name": network_name + "-allow-ssh",
            'properties': {
                "project": context.env['project'],
                "allowed": [
                    {
                        "IPProtocol": "tcp",
                        "ports": [
                            "22"
                        ]
                    }
                ],
                "description": "Allows TCP connections from any source to any instance on the network using port 22.",
                "direction": "INGRESS",
                "network": f"$(ref.{network_name}.selfLink)",
                "priority": 65534,
                "sourceRanges": [
                    "0.0.0.0/1"
                ]
            }
        }
    ]

    return {'resources': resources}
