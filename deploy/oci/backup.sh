#!/bin/sh
# Nightly backup of /opt/dcss/data to the OCI bucket crawl-backup using the instance's own identity
# (dynamic group crawl-vm; no API keys on the VM). Objects expire after 30 days via the bucket lifecycle rule.
# Set HC_PING_URL (e.g. a healthchecks.io check) in the cron file to get told when a night's backup is missing.
set -eu
DATA=/opt/dcss/data
NAME="dcss-data-$(date -u +%Y-%m-%dT%H%M).tgz"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"; rm -f "$DATA"/*.db3.snap' EXIT

# Consistent copies of the account and settings databases via SQLite's online backup API, taken in the running
# container. If that fails (e.g. the container is down) the raw files are archived instead.
set -- --exclude=data/sockets --exclude='data/saves/cache.*'
if docker exec dcss python3 -c '
import sqlite3
for n in ("passwd", "settings"):
    src, dst = sqlite3.connect(f"/data/{n}.db3"), sqlite3.connect(f"/data/{n}.db3.snap")
    src.backup(dst)
    dst.close()
    src.close()
'; then
  # a live -journal next to the snapshot would be rolled back into it on restore
  set -- "$@" --exclude=data/passwd.db3 --exclude=data/settings.db3 --exclude='data/*.db3-journal' \
    --transform='s,\.db3\.snap$,.db3,'
else
  echo "warning: database snapshot failed, archiving the live files" >&2
fi

# tar exits 1 when a file changes while it is read (a save during play); the archive is still usable
rc=0
tar czf "$TMP/$NAME" --warning=no-file-changed -C /opt/dcss "$@" data || rc=$?
[ "$rc" -le 1 ] || exit "$rc"

/opt/oci/bin/oci os object put --auth instance_principal --bucket-name crawl-backup \
  --name "$NAME" --file "$TMP/$NAME" --force >/dev/null
echo "$(date -u +%FT%TZ) backup ok $NAME ($(du -h "$TMP/$NAME" | cut -f1))"
if [ -n "${HC_PING_URL:-}" ]; then curl -fsS -m 10 --retry 3 -o /dev/null "$HC_PING_URL" || true; fi
