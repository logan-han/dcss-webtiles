#!/usr/bin/env python3
"""Snap restyled tiles back onto each original tile's own palette (keeps DCSS colour coding).

  python tools/palette_lock.py <src_dir> <generated_dir> <out_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image


def lock(orig_path: Path, gen_path: Path, dest: Path) -> None:
    oa = np.array(Image.open(orig_path).convert("RGBA"))
    alpha = oa[:, :, 3]
    opaque = oa[alpha > 0][:, :3] if (alpha > 0).any() else oa[:, :, :3].reshape(-1, 3)
    colours = np.unique(opaque, axis=0)
    if len(colours) > 256:
        strip = Image.fromarray(opaque.reshape(1, -1, 3), "RGB").quantize(
            colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        colours = np.array(strip.getpalette()[:768]).reshape(-1, 3)
    pal = Image.new("P", (1, 1))
    flat = colours.flatten().tolist()
    pal.putpalette(flat + [0] * (768 - len(flat)))
    ga = np.array(Image.open(gen_path).convert("RGBA"))
    q = Image.fromarray(ga[:, :, :3], "RGB").quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
    res = np.dstack([np.asarray(q), alpha]).astype(np.uint8)
    res[alpha == 0, :3] = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(res, "RGBA").save(dest)


def main() -> None:
    src, gen, out = (Path(a) for a in sys.argv[1:4])
    n = 0
    for p in gen.rglob("*.png"):
        rel = p.relative_to(gen)
        if (src / rel).exists():
            lock(src / rel, p, out / rel)
            n += 1
    print(f"palette-locked {n} tiles -> {out}")


if __name__ == "__main__":
    main()
