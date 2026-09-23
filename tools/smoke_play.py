"""Smoke test run inside the image (tools/smoke.sh pipes it to `docker exec -i <container> python3 -`).

Registers an account over the webtiles websocket, starts a game, then checks over HTTP that the lobby, the patched
client and every 1x/2x tile sheet are served, and that /gamedata refuses path traversal. Only needs what the image
already has (tornado).
"""
from __future__ import annotations

import asyncio
import json
import struct
import sys
import urllib.error
import urllib.request

from tornado.websocket import websocket_connect

BASE = "http://127.0.0.1:8080"
SHEETS = ["floor", "wall", "feat", "main", "player", "icons", "gui"]
failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


def get(path: str) -> tuple[int, dict, bytes]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""


def png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


async def play() -> dict:
    ws = await websocket_connect("ws://127.0.0.1:8080/socket", subprotocols=["no-compression"])
    await ws.write_message(json.dumps({"msg": "register", "username": "smoke", "password": "smoke-pass-1", "email": ""}))
    seen, client = set(), None
    for _ in range(2000):
        raw = await asyncio.wait_for(ws.read_message(), 30)
        if raw is None:
            sys.exit("websocket closed; saw " + ", ".join(sorted(seen)))
        data = json.loads(raw)
        for m in data.get("msgs", [data]):
            t = m.get("msg")
            seen.add(t)
            if t in ("register_fail", "login_fail"):
                sys.exit(f"{t}: {m}")
            if t == "login_success":
                await ws.write_message(json.dumps({"msg": "play", "game_id": "dcss-web-0.34"}))
            if t == "game_client":
                client = m
            # the dungeon view, not just chargen (which already sends "player")
            if client and "game_started" in seen and t == "map":
                ws.close()
                return client
    sys.exit("game never started; saw " + ", ".join(sorted(seen)))


def main() -> None:
    client = asyncio.run(play())
    check(True, "registered and started a game")
    check("data-sheet-scale" in client.get("content", ""), "game.html has the 2x sheet switch (patch 01)")
    v = client["version"]

    status, _, _ = get("/")
    check(status == 200, f"lobby / -> {status}")
    status, _, body = get(f"/gamedata/{v}/cell_renderer.js")
    check(status == 200 and b"data-sheet-scale" in body, f"cell_renderer.js is patched (patch 02) -> {status}")
    for name in SHEETS:
        s1, headers, one = get(f"/gamedata/{v}/{name}.png")
        s2, _, two = get(f"/gamedata/{v}/{name}-2x.png")
        a, b = png_size(one), png_size(two)
        check(s1 == s2 == 200 and a is not None and b == (a[0] * 2, a[1] * 2), f"{name}.png {a} and {name}-2x.png {b}")
    cache = headers.get("Cache-Control")
    check(cache == "no-cache", f"/gamedata sends Cache-Control: no-cache (patch 03) -> {cache}")

    for probe in ["../../../../../../etc/passwd", "..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd",
                  "%2e%2e%2f%2e%2e%2f%2e%2e%2f%2e%2e%2f%2e%2e%2f%2e%2e%2fdata%2fpasswd.db3", "/etc/passwd"]:
        status, _, _ = get(f"/gamedata/{v}/{probe}")
        check(status == 404, f"traversal {probe} -> {status} (patch 03)")

    if failures:
        sys.exit(f"{len(failures)} check(s) failed")


if __name__ == "__main__":
    main()
