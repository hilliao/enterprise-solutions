#!/bin/bash
set -e # exit the script when execution hits any error

export NAMESPACE=dev

kubectl create ns dev
kubectl label namespace $NAMESPACE istio-injection=enabled
kubectl apply -n $NAMESPACE -f deployment-v1.yaml
kubectl apply -n $NAMESPACE -f deployment-v2.yaml
envsubst < destination-rule-template.yaml > destinationrule.yaml
kubectl apply -n $NAMESPACE -f destinationrule.yaml
kubectl apply -n $NAMESPACE -f service.yaml

envsubst < virtual-service-template.yaml > virtual-service.yaml
kubectl apply -f virtual-service.yaml
kubectl apply -f gateway.yaml

export INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
export INGRESS_PORT=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="http2")].port}')
export SECURE_INGRESS_PORT=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="https")].port}')
export TCP_INGRESS_PORT=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="tcp")].port}')

echo "Wait for a few seconds then execute curl -v http://$INGRESS_HOST/apis/$NAMESPACE/vssubset as deployments take time"
response=null
set +e
while [ "$response" != "200" ]
do
  response=$(curl --write-out '%{http_code}' --silent --output /dev/null http://$INGRESS_HOST/apis/$NAMESPACE/vssubset)
  echo -n -e "$response returned\r"
done
echo ""
set -e

echo "Creating TLS certificates and the secure gateway..."
sh ./create-https-gateway.sh

echo "sleep for few seconds then execute curl -v -k https://$INGRESS_HOST/apis/$NAMESPACE/vssubset"
response=null
set +e
while [ "$response" != "200" ]
do
  response=$(curl --write-out '%{http_code}' --silent --output /dev/null -k https://$INGRESS_HOST/apis/$NAMESPACE/vssubset)
  echo -n -e "$response returned\r"
done
echo ""
set -e