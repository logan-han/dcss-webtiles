#!/bin/sh
set -eu
if [ ! -w /data ]; then
  echo "entrypoint: /data is not writable by uid $(id -u) gid $(id -g); chown the host directory or change user:" >&2
  exit 1
fi
for d in rcs running ttyrecs sockets saves morgue; do mkdir -p "/data/$d"; done
# Nothing is running yet, so game locks and sockets left by a killed container are stale. Webtiles would otherwise
# SIGHUP whichever process now has the recorded PID, which in a fresh container can be another player's game.
rm -f /data/running/*.ttyrec /data/sockets/*.sock
cp /crawl/config.yml /tmp/webtiles-config.yml
# HTTP_XHEADERS=true takes the client IP from X-Real-IP. Only set it behind a proxy that overwrites that
# header (see deploy/oci/Caddyfile), otherwise clients can fake their address.
if [ "${HTTP_XHEADERS:-}" = "true" ]; then echo "http_xheaders: true" >> /tmp/webtiles-config.yml; fi
# LOBBY_URL (e.g. https://crawl.example.com/) completes the links printed by `server.py password --reset`
if [ -n "${LOBBY_URL:-}" ]; then echo "lobby_url: \"$LOBBY_URL\"" >> /tmp/webtiles-config.yml; fi
cd /crawl/source
exec python3 webserver/server.py
