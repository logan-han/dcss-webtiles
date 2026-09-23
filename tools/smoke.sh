#!/bin/sh
# Start an image the way the compose files do (non-1000 uid, read-only root, tmpfs /tmp) with a scratch /data,
# run tools/smoke_play.py inside it, then check the game was saved and the server exits 0 on SIGTERM.
#   tools/smoke.sh <image>
set -eu
IMAGE="$1"
HERE=$(cd "$(dirname "$0")" && pwd)
NAME="dcss-smoke-$$"
DATA=$(mktemp -d)
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then echo "--- container log"; docker logs "$NAME" 2>&1 | tail -50 || true; fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$DATA"
  exit "$status"
}
trap cleanup EXIT
# skip character selection so the game gets far enough to have a save file (init-player.sh keeps an existing rc)
mkdir "$DATA/rcs" && printf 'species = Human\nbackground = Monk\nweapon = unarmed\n' > "$DATA/rcs/smoke.rc"
# never uid 1000, so a write under /crawl (owned by crawl) would show up as a failure
if [ "$(id -u)" = 0 ]; then RUNAS=1026:100; chown -R "$RUNAS" "$DATA"; else RUNAS="$(id -u):$(id -g)"; fi

docker run -d --name "$NAME" --user "$RUNAS" --read-only --tmpfs /tmp --security-opt no-new-privileges \
  -v "$DATA:/data" "$IMAGE" >/dev/null
up=0
for _ in $(seq 60); do
  if docker exec "$NAME" python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=2)" 2>/dev/null
  then up=1; break; fi
  sleep 1
done
[ "$up" = 1 ] || { echo "server did not come up in 60s" >&2; exit 1; }

docker exec -i "$NAME" python3 - < "$HERE/smoke_play.py"

# webtiles SIGHUPs a game when its player disconnects or the server gets SIGTERM, and crawl saves on SIGHUP
docker stop -t 30 "$NAME" >/dev/null
code=$(docker inspect -f '{{.State.ExitCode}}' "$NAME")
[ "$code" = 0 ] || { echo "server exited $code on SIGTERM" >&2; exit 1; }
[ -s "$DATA/saves/smoke.cs" ] || { echo "no save file after stop" >&2; ls -la "$DATA/saves" >&2; exit 1; }
echo "ok   game saved and server stopped cleanly"
