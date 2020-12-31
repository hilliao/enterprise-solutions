#!/bin/bash
set -e # exit the script when execution hits any error

openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -subj '/O=techsightteam Inc./CN=techsightteam.com' -keyout techsightteam.com.key -out techsightteam.com.crt
openssl req -out dev.techsightteam.com.csr -newkey rsa:2048 -nodes -keyout dev.techsightteam.com.key -subj "/CN=dev.techsightteam.com/O=dev organization"
openssl x509 -req -days 365 -CA techsightteam.com.crt -CAkey techsightteam.com.key -set_serial 0 -in dev.techsightteam.com.csr -out dev.techsightteam.com.crt

# Istio 1.8: kubectl create -n istio-system secret tls dev-credential --key=dev.techsightteam.com.key --cert=dev.techsightteam.com.crt
# for Istio 1.4
kubectl create -n istio-system secret tls istio-ingressgateway-certs --key=dev.techsightteam.com.key --cert=dev.techsightteam.com.crt
echo "polling the TLS certificate mount status on istio ingressgateway's pods"
set +e
until [ -n "$TLS_MOUNTED" ]
do
  TLS_MOUNTED=`kubectl exec -it -n istio-system $(kubectl -n istio-system get pods -l istio=ingressgateway -o jsonpath='{.items[0].metadata.name}') -- ls -al /etc/istio/ingressgateway-certs | grep tls`
  echo -n -e "Mount status: $TLS_MOUNTED \r"
done
echo ""

set -e # exit the script when execution hits any error
cat <<EOF | kubectl apply -f -
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: https-gw
spec:
  selector:
    istio: ingressgateway # use istio default ingress gateway
  servers:
  - port:
      number: 443
      name: https
      protocol: HTTPS
    tls:
      mode: SIMPLE
      # Istio 1.8: credentialName: dev-credential # must be the same as secret
      serverCertificate: /etc/istio/ingressgateway-certs/tls.crt # Istio 1.4
      privateKey: /etc/istio/ingressgateway-certs/tls.key # Istio 1.4
    hosts:
    - "*"
EOF
