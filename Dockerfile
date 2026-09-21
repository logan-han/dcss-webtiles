# syntax=docker/dockerfile:1
ARG DCSS_VERSION=0.34.1

# ---------- build: compile DCSS with webtiles support ----------
FROM debian:bookworm-slim AS build
ARG DCSS_VERSION
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bison flex pkg-config ca-certificates curl xz-utils \
    libncursesw5-dev liblua5.4-dev libsqlite3-dev libz-dev libpng-dev libpcre3-dev \
    python3 python3-yaml python-is-python3 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o dcss.tar.xz \
      "https://github.com/crawl/crawl/releases/download/${DCSS_VERSION}/stone_soup-${DCSS_VERSION}.tar.xz" \
 && mkdir crawl && tar -xJf dcss.tar.xz -C crawl --strip-components=1 && rm dcss.tar.xz
# hand-fixed tiles, same relative paths as rltiles/ (empty by default)
COPY tiles/overrides/ /src/crawl/source/rltiles/
WORKDIR /src/crawl/source
# the Makefile shells out to git for the version string; the release tarball has none
RUN printf '#!/bin/sh\ncase "$1" in describe) cat /src/crawl/source/util/release_ver ;; rev-parse) echo release ;; *) exit 1 ;; esac\n' \
      > /usr/local/bin/git && chmod +x /usr/local/bin/git
# 0.34.1 Makefile typo ($(RLTILES)status-icon-sizes.h, no slash) makes this a parallel-make race; generate it first
RUN python3 util/status-icon-sizes-gen.py rltiles/icon-sizes.txt \
 && make -j"$(nproc)" WEBTILES=y USE_DGAMELAUNCH=y \
 && strip crawl && ls -la crawl webserver/game_data/static/*.png

# ---------- hd: 2x tile sheets (xBR) for high-DPI screens ----------
FROM python:3.12-slim-bookworm AS hd
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pillow numpy
WORKDIR /work
COPY --from=build /src/crawl/source/webserver/game_data/static/ ./static/
COPY tools/hd_sheets.py ./
RUN python hd_sheets.py static out && ls -la out

# ---------- runtime: webtiles server ----------
FROM python:3.12-slim-bookworm AS runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libncursesw6 liblua5.4-0 libsqlite3-0 zlib1g libpcre3 patch \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 1000 --create-home --home-dir /crawl crawl
WORKDIR /crawl/source
COPY --from=build /src/crawl/source/crawl ./crawl
COPY --from=build /src/crawl/source/dat ./dat
COPY --from=build /src/crawl/source/webserver ./webserver
COPY --from=build /src/crawl/settings /crawl/settings
COPY --from=build /src/crawl/docs /crawl/docs
RUN pip install --no-cache-dir -r webserver/requirements/base.py3.txt
# our server config, game list, patches and the 2x sheets
COPY server/patches/ /tmp/patches/
RUN for p in /tmp/patches/*.patch; do patch -p1 < "$p"; done && rm -rf /tmp/patches
COPY --from=hd /work/out/ ./webserver/game_data/static/
COPY server/config.yml ./webserver/config.yml
RUN rm -f webserver/games.d/*.yaml webserver/games.d/*.yml
COPY server/games.d/ ./webserver/games.d/
COPY server/init-player.sh server/entrypoint.sh /crawl/
RUN chmod +x /crawl/init-player.sh /crawl/entrypoint.sh && chown -R crawl:crawl /crawl
USER crawl
EXPOSE 8080
VOLUME ["/data"]
ENTRYPOINT ["/crawl/entrypoint.sh"]
