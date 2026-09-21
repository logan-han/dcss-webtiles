#!/bin/sh
# Point crawl.han.life at the VM. han.life is hosted in Lightsail DNS (us-east-1), not Route 53.
#   deploy/oci/dns.sh <public-ip>
set -eu
IP="$1"; DOMAIN=han.life; NAME="crawl.$DOMAIN"
aws lightsail get-domain --region us-east-1 --domain-name "$DOMAIN" \
  --query "domain.domainEntries[?name=='$NAME'].join('', ['name=', name, ',target=', target, ',type=', type])" --output text |
tr '\t' '\n' | sed '/^$/d' |
while read -r entry; do
  echo "removing $entry"
  aws lightsail delete-domain-entry --region us-east-1 --domain-name "$DOMAIN" --domain-entry "$entry" --query 'operation.status' --output text
done
aws lightsail create-domain-entry --region us-east-1 --domain-name "$DOMAIN" \
  --domain-entry "name=$NAME,target=$IP,type=A" --query 'operation.status' --output text
echo "$NAME -> $IP"
