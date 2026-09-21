#!/bin/sh
# Called by webtiles with the player name on registration: seed their rc from the default settings.
set -eu
name="$1"
mkdir -p /data/rcs /data/running "/data/ttyrecs/$name" "/data/morgue/$name"
[ -f "/data/rcs/$name.rc" ] || cp /crawl/settings/init.txt "/data/rcs/$name.rc"
