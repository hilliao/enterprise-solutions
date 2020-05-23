#!/bin/ash

# docker run -e USER=username -e PASS=password -e HOST=dynu_hostname -d --restart unless-stopped --name=dynu-client hilliao/dynu-client:0.0

# set Cloud SQL password and store it in secret manager
set -e # exit the script when execution hits any error
set -x # print the executing lines

# find the current host's public IP address and update dynamic DNS
while [ true ]; do
  export IP=$(dig TXT +short o-o.myaddr.l.google.com @ns1.google.com | awk -F'"' '{ print $2}')
  curl "https://$USER:$PASS@api.dynu.com/nice/update?hostname=$HOST&myip=$IP" && echo ''
  sleep 200
done
