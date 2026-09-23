# syntax=docker/dockerfile:1
ARG DCSS_VERSION=0.34.1
# sha256 of the release tarball: change it together with DCSS_VERSION
ARG DCSS_SHA256=473b9cdc16be0b537ac11e43c6c77db4b290000e4a17f72a842eba59c6b7be2a

# ---------- build: compile DCSS with webtiles support ----------
FROM debian:bookworm-slim AS build
ARG DCSS_VERSION
ARG DCSS_SHA256
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bison flex pkg-config ca-certificates curl xz-utils \
    libncursesw5-dev liblua5.4-dev libsqlite3-dev libz-dev libpng-dev \
    python3 python3-yaml python-is-python3 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o dcss.tar.xz \
      "https://github.com/crawl/crawl/releases/download/${DCSS_VERSION}/stone_soup-${DCSS_VERSION}.tar.xz" \
 && echo "${DCSS_SHA256}  dcss.tar.xz" | sha256sum -c - \
 && mkdir crawl && tar -xJf dcss.tar.xz -C crawl --strip-components=1 && rm dcss.tar.xz
# hand-fixed tiles, same relative paths as rltiles/ (empty by default); each one must replace an existing tile
COPY tools/verify_tiles.py /src/
COPY tiles/overrides/ /src/overrides/
RUN python3 /src/verify_tiles.py /src/overrides --against /src/crawl/source/rltiles \
 && cp -R /src/overrides/. /src/crawl/source/rltiles/
WORKDIR /src/crawl/source
# the Makefile shells out to git for the version string; the release tarball has none
RUN printf '#!/bin/sh\ncase "$1" in describe) cat /src/crawl/source/util/release_ver ;; rev-parse) echo release ;; *) exit 1 ;; esac\n' \
      > /usr/local/bin/git && chmod +x /usr/local/bin/git
# 0.34.1 Makefile typo ($(RLTILES)status-icon-sizes.h, no slash) makes this a parallel-make race; generate it first
RUN python3 util/status-icon-sizes-gen.py rltiles/icon-sizes.txt \
 && make -j"$(nproc)" WEBTILES=y USE_DGAMELAUNCH=y \
 && strip crawl && ls -la crawl webserver/game_data/static/*.png

# ---------- web: webserver tree with our patches (kept out of build so a patch edit doesn't recompile) ----------
FROM build AS web
COPY server/patches/ /tmp/patches/
# Every patch must apply exactly: no fuzz, no already-applied hunks, no .orig files left in the served tree.
# dat/tiles holds the 1x sheets and title art for local tiles, which a WEBTILES binary never reads.
# webtiles only reads webserver/config.yml; it links to /tmp so entrypoint.sh can add settings as any uid.
RUN set -e; for p in /tmp/patches/*.patch; do patch -p1 --forward --batch --fuzz=0 --no-backup-if-mismatch < "$p"; done \
 && rm -rf /tmp/patches dat/tiles webserver/games.d/*.yaml webserver/games.d/*.yml \
 && ln -s /tmp/webtiles-config.yml webserver/config.yml

# ---------- hd: 2x tile sheets (xBR) for high-DPI screens ----------
FROM python:3.12-slim-bookworm AS hd
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pillow==12.3.0 numpy==2.5.3
WORKDIR /work
COPY --from=build /src/crawl/source/webserver/game_data/static/ ./static/
COPY tools/hd_sheets.py ./
RUN python hd_sheets.py static out && ls -la out

# ---------- runtime: webtiles server ----------
# Python 3.12: webtiles/userdb.py imports crypt, which 3.13 removed
FROM python:3.12-slim-bookworm AS runtime
ARG DCSS_VERSION
LABEL org.opencontainers.image.title="dcss-webtiles" \
      org.opencontainers.image.description="Dungeon Crawl Stone Soup webtiles server with 2x tile sheets" \
      org.opencontainers.image.source="https://github.com/logan-han/dcss-webtiles" \
      org.opencontainers.image.version="${DCSS_VERSION}"
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libncursesw6 liblua5.4-0 libsqlite3-0 zlib1g \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 1000 --create-home --home-dir /crawl crawl \
 && install -d -o crawl -g crawl /data
WORKDIR /crawl/source
COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
# everything below is root-owned and read-only to the server; all state lives in /data
COPY --from=build /src/crawl/source/crawl ./crawl
COPY --from=web /src/crawl/source/dat ./dat
COPY --from=web /src/crawl/source/webserver ./webserver
COPY --from=build /src/crawl/settings /crawl/settings
COPY --from=build /src/crawl/docs /crawl/docs
COPY --from=hd /work/out/ ./webserver/game_data/static/
COPY server/config.yml /crawl/config.yml
COPY server/games.d/ ./webserver/games.d/
COPY --chmod=755 server/init-player.sh server/entrypoint.sh /crawl/
USER crawl
EXPOSE 8080
# new named/anonymous volumes copy /data's ownership (crawl); bind mounts must be writable by the container's uid
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=5)"]
ENTRYPOINT ["/crawl/entrypoint.sh"]
