# dcss-webtiles

Dungeon Crawl Stone Soup webtiles server as a single container, built from the 0.34.1 release,
with 2x xBR tile sheets for high-DPI screens.

- `Dockerfile` builds DCSS (`WEBTILES=y USE_DGAMELAUNCH=y`), generates the 2x sheets and ships
  the webtiles server on port 8080 with all state under `/data`.
- `server/` holds the webtiles overrides, game list, player init and the two client patches.
- `compose.yaml` is the Container Manager project for the NAS; the image is published to Docker Hub as `loganhan123/dcss-webtiles` by CI.
- `tools/hd_sheets.py` makes the 2x sheets; `pilot/` holds the tile experiments.

Local run: `docker build -t dcss-webtiles . && docker run --rm -p 8080:8080 -v $PWD/data:/data dcss-webtiles`

## Hosting options

- NAS: `compose.yaml` (Container Manager), port 7777 on the LAN.
- Oracle Cloud Always Free (or any VM): `deploy/oci/` has the compose file with Caddy for automatic HTTPS, a cloud-init
  script for the instance and a Lightsail DNS helper for `crawl.han.life`.

Images on Docker Hub are multi-arch (amd64 for the NAS, arm64 for Ampere A1 and Apple Silicon).
