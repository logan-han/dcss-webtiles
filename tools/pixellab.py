#!/usr/bin/env python3
"""Make pixel art with PixelLab (https://www.pixellab.ai) through its MCP server, under a generation cap.

The token is the account's API secret (pixellab.ai/account) in PIXELLAB_SECRET. Only the MCP endpoint can spend the
free daily generations (+5 a day at midnight UTC, kept up to 20); the REST API answers 402 once the subscription
and credit are gone, and neither balance call reports the daily pool, so --max-generations is the real guard.

  balance                                  subscription and credit as the API reports them (free)
  image "<description>" <out.png>          one image, 1 generation; this made server/static/lobby-banner.png:
    python tools/pixellab.py image "wide banner of a dark stone dungeon hall, flickering wall torches, ..." \\
        server/static/lobby-banner.png --size 512x128 --model pixen --seed 7

Pixen takes sides divisible by 4 up to a 512x512 area; pixflux takes 16-400 a side up to a 400x400 area and is
the one with an init image. correct_pixelart was tried on the xBR 2x sheets at strengths 0.1-0.6 and only added
colour noise or blurred the textures (pilot/pixellab_correct_*.png), so there is no sheet polish command.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MCP = "https://api.pixellab.ai/mcp"
IMAGE_COST = 1.0


class Mcp:
    """Minimal JSON-RPC client for the streamable-HTTP MCP endpoint (SSE or JSON responses)."""

    def __init__(self, secret: str):
        self.secret, self.session = secret, None
        client = {"name": "dcss-webtiles", "version": "1"}
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": client})
        self.rpc("notifications/initialized", {}, notify=True)

    def rpc(self, method: str, params: dict, notify: bool = False) -> dict:
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            body["id"] = 1
        headers = {"Authorization": f"Bearer {self.secret}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(MCP, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                self.session = r.headers.get("Mcp-Session-Id") or self.session
                text = r.read().decode()
        except urllib.error.HTTPError as e:
            sys.exit(f"{method}: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
        if notify:
            return {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line.startswith("{"):
                msg = json.loads(line)
                if "error" in msg:
                    sys.exit(f"{method}: {msg['error']}")
                if "result" in msg:
                    return msg["result"]
        sys.exit(f"{method}: no result in {text[:300]}")

    def tool(self, name: str, args: dict) -> tuple[str, list[bytes]]:
        """Call a tool; returns its text and any inline images. Exits on a tool error (e.g. no generations left)."""
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        text = "\n".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        if r.get("isError"):
            sys.exit(f"{name}: {text[:600]}")
        return text, [base64.b64decode(c["data"]) for c in r.get("content", []) if c.get("type") == "image"]

    def job_image(self, submit_text: str, timeout: int = 600) -> bytes:
        """Wait for the job a raw-image tool just queued and return frame 0 as PNG bytes."""
        m = re.search(r"job_id: ([0-9a-f-]{36})", submit_text)
        if not m:
            sys.exit(f"no job id in: {submit_text[:600]}")
        job, deadline = m.group(1), time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.tool("wait_for_jobs", {"timeout_seconds": 120})
            text, images = self.tool("get_image", {"job_id": job})
            if images:
                return images[0]
            if "failed" in text.lower():
                sys.exit(f"job {job} failed: {text[:600]}")
            time.sleep(3)
        sys.exit(f"job {job}: still running after {timeout}s")


def cmd_balance(args, mcp: Mcp) -> None:
    text, _ = mcp.tool("get_balance", {})
    print(text)
    print("(free daily generations are not included; the account page shows them)")


def cmd_image(args, mcp: Mcp) -> None:
    if IMAGE_COST > args.max_generations:
        sys.exit(f"an image costs {IMAGE_COST:g} generation, over --max-generations {args.max_generations:g}")
    w, h = (int(v) for v in args.size.lower().split("x"))
    payload = {"description": args.description, "width": w, "height": h, "no_background": args.no_background, "detail": "highly detailed"}
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.model == "pixflux":
        payload["shading"] = "detailed shading"
    text, _ = mcp.tool(f"create_image_{args.model}", payload)
    cost = re.search(r"cost: .*", text)
    print(f"queued ({cost.group(0) if cost else 'cost unknown'})", flush=True)
    png = mcp.job_image(text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"wrote {out} ({len(png)} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balance").set_defaults(fn=cmd_balance)
    p = sub.add_parser("image")
    p.add_argument("description")
    p.add_argument("out")
    p.add_argument("--size", default="512x128", help="WxH (default 512x128)")
    p.add_argument("--model", default="pixen", choices=["pixen", "pixflux"])
    p.add_argument("--seed", type=int)
    p.add_argument("--no-background", action="store_true")
    p.add_argument("--max-generations", type=float, default=1, help="refuse to spend more than this (default 1)")
    p.set_defaults(fn=cmd_image)
    args = ap.parse_args()
    secret = os.environ.get("PIXELLAB_SECRET")
    if not secret:
        sys.exit("set PIXELLAB_SECRET (pixellab.ai/account)")
    args.fn(args, Mcp(secret))


if __name__ == "__main__":
    main()
