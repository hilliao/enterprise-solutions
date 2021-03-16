# Nginx or Apache Canary Deployment Sample
Automated scripts to create canary deployment on GKE Istio 1.4.x; there are 2 deployments: nginx and apache. The nginx
deployment has 90% of the hits. The apache deployment has 10% of the hits serving as the beta rollout.

## Create a GKE cluster with Istio
Wait until the Istio Ingress Gateway IP gets created in the watch command.
```shell
PROJECT_ID=
GKE_NAME=istio-1
ZONE=us-central1-c
NET=default
SUBNET=default


gcloud beta container --project $PROJECT_ID clusters create $GKE_NAME --zone $ZONE --no-enable-basic-auth --machine-type "e2-medium" --image-type "COS" --disk-type "pd-ssd" --disk-size "50" --metadata disable-legacy-endpoints=true --scopes "https://www.googleapis.com/auth/cloud-platform" --max-pods-per-node "110" --num-nodes "2" --enable-stackdriver-kubernetes --enable-ip-alias --network $NET --subnetwork $SUBNET --default-max-pods-per-node "110" --no-enable-master-authorized-networks --addons HorizontalPodAutoscaling,HttpLoadBalancing,Istio --istio-config auth=MTLS_PERMISSIVE --no-enable-autoupgrade --enable-autorepair --max-surge-upgrade 1 --max-unavailable-upgrade 0 --autoscaling-profile optimize-utilization --workload-pool "$PROJECT_ID.svc.id.goog"
watch kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```
Evaluate and execute 1 by 1 the commands in script to deploy cluster resources. The command stops at polling the curl
until 200 is returned. Notice comments before each command to decide what to execute depending on the condinoit
such as Istio version.
```shell
sh deploy-canary-istio.sh
namespace/dev created
namespace/dev labeled
deployment.apps/canary-deployment-v1 created
deployment.apps/canary-deployment-v2 created
destinationrule.networking.istio.io/canary-destination created
service/canary-svc created
virtualservice.networking.istio.io/canary created
gateway.networking.istio.io/http-gw created
Wait for a few seconds then execute curl -v http://$INGRESS_HOST_IP/apis/dev/vssubset as deployments take time
503 returned
```

The command stops again at polling the [Istio 1.4 secure gateway filemount](https://istio.io/v1.4/docs/tasks/traffic-management/ingress/secure-ingress-mount/)

```shell
200 returned
Creating TLS certificates and the secure gateway...
Generating a RSA private key
......+++++
.................................................+++++
writing new private key to 'techsightteam.com.key'
-----
Generating a RSA private key
......................................................................+++++
.............................+++++
writing new private key to 'dev.techsightteam.com.key'
-----
Signature ok
subject=CN = dev.techsightteam.com, O = dev organization
Getting CA Private Key
secret/istio-ingressgateway-certs created
polling the TLS certificate mount status on istio ingressgateway's pods
Mount status:
```

Normally, it takes less than 1 minute. At success, the following shows

```shell
Mount status: lrwxrwxrwx 1 root root   14 Dec 31 06:41 tls.crt -> ..data/tls.crt
 rwxrwxrwx 1 root root   14 Dec 31 06:41 tls.key -> ..data/tls.key
gateway.networking.istio.io/https-gw created
sleep for few seconds then execute curl -v -k https://$INGRESS_HOST_IP/apis/dev/vssubset
200 returned
```

## Testing
The curl commands return 90% of Nginx, 10% of Apache. Modify the virtual service to change the weights
```shell
kubectl edit vs canary
```