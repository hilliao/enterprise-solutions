# Book Info traffic split Sample
Download the sample code from [the Istio example](https://istio.io/latest/docs/examples/bookinfo/).
Some values in the yaml files are hard coded:

0. `gateways:`'s value in the virtual service.
0. `default` as the namespace in the virtual service.

## Getting started
### Prerequisites
Google cloud Anthos service mesh > 1.9 installed.

Book info GKE resources deployed per `kubectl apply -f samples/bookinfo/platform/kube/bookinfo.yaml
`. The namespace for deployments has auto Istio sidecar injection:
```shell
NAMESPACE=default
kubectl -n istio-system get pods -l app=istiod --show-labels | grep istio.io/rev= || \
# copy and paste the value after = to the command below; the example value here is asm-191-1
kubectl label namespace $NAMESPACE istio-injection- istio.io/rev=asm-191-1 --overwrite
```

### deploy the GKE parts of the resources per [the intructions](https://istio.io/latest/docs/examples/bookinfo/)
kubectl apply -f samples/bookinfo/platform/kube/bookinfo.yaml

## Creating service mesh resources
Inspect comments in each yaml files before applying them. Recommended creation order:
**destination rules > virtual services** 

## Testing
### Verify the main page
Execute the following commands to get the Istio ingress gateway's IP and show the Book info page
```shell
export INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo $INGRESS_HOST
curl http://$INGRESS_HOST/productpage -I
```
### Verify traffic split to reviews subsets
Virtual service `bookinfo` containing `gateways` splits traffic to reviews service from `istio-ingressgateway`.
```shell
watch curl http://$INGRESS_HOST/reviews/8
```
Expect the logs in reviews deployments to have `[WARNING ] No operation matching request path "/8" is found, Relative Path: /8`
depending on how `weight:` is configured.

## Verify traffic split within the service mesh
Virtual service `reviews` without `gateways` but with `hosts:` splits traffic to reviews service from a pod in the service mesh.
Execute `curl` in a pod to test
```shell
kubectl apply -f gcloud.yaml
kubectl exec -it gcloud -- bash
curl -I http://reviews:9080/9 # execute multiple times to test
```
Expect the logs in reviews deployments to have `[WARNING ] No operation matching request path "/9" is found, Relative Path: /9`
depending on how `weight:` is configured.
