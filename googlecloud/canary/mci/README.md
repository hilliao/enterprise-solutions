# Anthos multi cluster ingress sample code
Example of how to configure Nginx and Apache web servers with GKE multi cluster ingress 
## Install Anthos service mesh on 2 GKE clusterss
Create 2 GKE clusters and install Anthos service mesh per [the instructions of Mesh CA](https://hilliao.medium.com/gke-with-istio-and-config-sync-37f0f1302d65).
Ctrl+F to find `hub-meshca` in the article on how to install Anthos service mesh with Mesh CA.
## Enable multi cluster ingress
Follow [the instructions](https://cloud.google.com/kubernetes-engine/docs/how-to/multi-cluster-ingress-setup#registering_your_clusters)
to register and configure the clusters. If you followed the Mesh CA option during Anthos service mesh installation,
the GKE clusters have already been registered to the hub.
## Deploy multi cluster service, ingress
Read [the instructions](https://cloud.google.com/kubernetes-engine/docs/how-to/multi-cluster-ingress) as the sample code
followed the instructions.

0. Deploy ../nginx-or-apache/deployment-v1.yaml, ../nginx-or-apache/deployment-v2.yaml to both clusters
0. In the config cluster, Deploy service.yaml
0. In the config cluster, Deploy ingress.yaml as it depends on service.yaml

## Known iusse
If the health check on the deployment's pods are at a HTTP path other than `/`, the annotations of 
[BackendConfig in Ingress](https://cloud.google.com/kubernetes-engine/docs/how-to/ingress-features#associating_backendconfig_with_your_ingress)
is not effective. Manually modifying the health check will cause the external load balancing's IP to succeed in a few minutes 
before the health check reverts back to `/`. 