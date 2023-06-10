import json

with open('config.json', 'r') as f_config:
    configuration_str = f_config.read()

configuration = json.loads(configuration_str)
with open(configuration['deployments'], 'r') as f_depl:
    depl_str = f_depl.read()

deployments = json.loads(depl_str)
with open(configuration['cmd-replicas'], 'w') as f_cmd, open(configuration['cmd-0-replicas'], 'w') as f_cmd_0:
    for depl in deployments["items"]:
        if depl['metadata']['namespace'] == 'kube-system':
            continue
        else:
            f_cmd.write(
                f"kubectl scale deployment/{depl['metadata']['name']} --replicas={depl['spec']['replicas']} --namespace {depl['metadata']['namespace']}\n")
            f_cmd_0.write(
                f"kubectl scale deployment/{depl['metadata']['name']} --replicas=0 --namespace {depl['metadata']['namespace']}\n")
