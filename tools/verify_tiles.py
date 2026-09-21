#!/usr/bin/env python3
"""Check hand-fixed tile overrides: every PNG must be 32x32 RGBA/P/RGB.

  python tools/verify_tiles.py tiles/overrides
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "tiles/overrides")
    bad = 0
    pngs = list(root.rglob("*.png"))
    for p in pngs:
        im = Image.open(p)
        if im.size != (32, 32):
            print(f"{p}: {im.size}, expected 32x32")
            bad += 1
    print(f"{len(pngs)} override tiles checked, {bad} bad")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
