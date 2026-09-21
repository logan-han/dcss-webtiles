#!/bin/sh
# Point crawl.han.life at the VM: replaces whatever record exists (the CNAME to synology.me) with an A record.
#   deploy/oci/dns.sh <public-ip>
set -eu
IP="$1"; NAME="crawl.han.life."
ZONE=$(aws route53 list-hosted-zones-by-name --dns-name han.life --query 'HostedZones[0].Id' --output text | sed 's#/hostedzone/##')
EXISTING=$(aws route53 list-resource-record-sets --hosted-zone-id "$ZONE" --query "ResourceRecordSets[?Name=='$NAME']" --output json)
CHANGES=$(python3 - "$EXISTING" "$IP" "$NAME" <<'PY'
import json, sys
existing, ip, name = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3]
changes = [{"Action": "DELETE", "ResourceRecordSet": r} for r in existing]
changes.append({"Action": "CREATE", "ResourceRecordSet": {"Name": name, "Type": "A", "TTL": 300, "ResourceRecords": [{"Value": ip}]}})
print(json.dumps({"Comment": "crawl -> OCI", "Changes": changes}))
PY
)
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE" --change-batch "$CHANGES" --query 'ChangeInfo.Status' --output text
echo "crawl.han.life -> $IP"
