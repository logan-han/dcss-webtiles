#!/bin/sh
# Nightly backup of /opt/dcss/data to the OCI bucket crawl-backup using the instance's own identity
# (dynamic group crawl-vm; no API keys on the VM). Objects expire after 30 days via the bucket lifecycle rule.
set -eu
STAMP=$(date -u +%Y-%m-%dT%H%M)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
tar czf "$TMP/dcss-data-$STAMP.tgz" -C /opt/dcss data
/opt/oci/bin/oci os object put --auth instance_principal --bucket-name crawl-backup \
  --name "dcss-data-$STAMP.tgz" --file "$TMP/dcss-data-$STAMP.tgz" --force >/dev/null
echo "$(date -u +%FT%TZ) backup ok dcss-data-$STAMP.tgz ($(du -h "$TMP/dcss-data-$STAMP.tgz" | cut -f1))"
