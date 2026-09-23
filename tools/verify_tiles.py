#!/usr/bin/env python3
"""Check hand-fixed tile overrides before the build copies them over rltiles/.

Every override must be a PNG. With --against (the Dockerfile passes the DCSS source's rltiles/), each one must also
replace an existing tile at the same relative path; a typo'd path would otherwise add an unused file and the fix
would silently never ship. A size that differs from the upstream tile is reported but allowed. Standard library
only, so it runs in the build stage.

  python tools/verify_tiles.py tiles/overrides [--against <crawl>/source/rltiles]
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIG or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="tiles/overrides")
    ap.add_argument("--against", type=Path, help="upstream rltiles dir the overrides are copied over")
    args = ap.parse_args()
    root = Path(args.root)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != ".gitkeep")
    bad = 0
    for p in files:
        rel = p.relative_to(root)
        size = png_size(p)
        if size is None:
            print(f"{rel}: not a PNG")
            bad += 1
            continue
        if args.against is None:
            continue
        orig = args.against / rel
        if not orig.is_file():
            print(f"{rel}: no tile at this path under {args.against}")
            bad += 1
            continue
        orig_size = png_size(orig)
        if orig_size != size:
            print(f"{rel}: warning: {size[0]}x{size[1]}, the upstream tile is {orig_size[0]}x{orig_size[1]}" if orig_size
                  else f"{rel}: warning: the upstream tile is not a readable PNG")
    print(f"{len(files)} override files checked, {bad} bad")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
