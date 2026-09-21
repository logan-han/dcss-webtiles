#!/bin/sh
set -eu
for d in rcs running ttyrecs sockets saves morgue; do mkdir -p "/data/$d"; done
cd /crawl/source
exec python3 webserver/server.py
