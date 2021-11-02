# python script to generate kubectl commands to scale deployments
## generate the current state of deployments
`$ kubectl get deployments -A -o json > deployments.json`
## edit configuration file
In config.json
- "deployments": "deployments.json" is the input file of the deployments from kubectl command
- "cmd-replicas": "replicas.sh" is the output filename to restore deployment's replica numbers
- "cmd-0-replicas": "0-replicas.sh" is the output filename to scale deployments to 0 replica