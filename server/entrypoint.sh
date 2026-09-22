#!/bin/sh
set -eu
for d in rcs running ttyrecs sockets saves morgue; do mkdir -p "/data/$d"; done
cp /crawl/config.yml /tmp/webtiles-config.yml
# HTTP_XHEADERS=true takes the client IP from X-Real-IP. Only set it behind a proxy that overwrites that
# header (see deploy/oci/Caddyfile), otherwise clients can fake their address.
if [ "${HTTP_XHEADERS:-}" = "true" ]; then echo "http_xheaders: true" >> /tmp/webtiles-config.yml; fi
cd /crawl/source
exec python3 webserver/server.py
