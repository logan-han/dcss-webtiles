#!/usr/bin/env python3
"""Pack pilot tiles into canvases for PixelLab pixflux img2img (1 generation per canvas), and slice results back.

  python tools/pixellab_grids.py build          -> pilot/pixellab/<name>_init.png + .b64
  python tools/pixellab_grids.py slice <name> <result.png> <out_dir>
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grid_pilot import build_grid, slice_grid  # noqa: E402
from PIL import Image  # noqa: E402

TERRAIN = [
    "dngn/floor/grey_dirt0", "dngn/floor/lair0", "dngn/floor/pebble_brown0", "dngn/floor/floor_vines0",
    "dngn/wall/brick_brown0", "dngn/wall/catacombs0", "dngn/wall/stone_gray0", "dngn/wall/lair0",
    "dngn/doors/closed_door", "dngn/gateways/stone_stairs_down", "dngn/water/shallow_water", "dngn/water/deep_water",
    "dngn/altars/zin1", "dngn/trees/mangrove1", "dngn/statues/statue_archer", "dngn/traps/teleport",
]
SPRITES = [
    "mon/humanoids/ogre", "mon/unique/sigmund", "mon/animals/jackal", "mon/humanoids/orcs/orc",
    "mon/animals/rat", "mon/humanoids/gnoll", "mon/unique/grinder", "mon/animals/wolf",
    "player/base/human_m", "player/base/deep_elf_m", "item/potion/ruby", "item/potion/brilliant_blue",
    "item/weapon/long_sword1", "item/weapon/dagger", "item/armour/chain_mail1", "item/scroll/scroll",
]
GRIDS = {"terrain": (TERRAIN, 4, 0), "sprites": (SPRITES, 4, 8)}
SRC = Path("pilot/src")
OUT = Path("pilot/pixellab")


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    canvases = {}
    for name, (names, n, gutter) in GRIDS.items():
        canvas, alphas, cell = build_grid(SRC, names, n, gutter, 1)
        canvases[name] = canvas
        p = OUT / f"{name}_init.png"
        canvas.save(p, optimize=True)
        b64 = base64.b64encode(p.read_bytes()).decode()
        (OUT / f"{name}_init.b64").write_text(b64)
        meta[name] = {"size": canvas.size, "cell": cell, "n": n, "gutter": gutter, "png_bytes": p.stat().st_size, "b64_chars": len(b64)}
    # combined: terrain left, sprites right
    t, s = canvases["terrain"], canvases["sprites"]
    combo = Image.new("RGB", (t.width + s.width, max(t.height, s.height)), (36, 36, 36))
    combo.paste(t, (0, 0))
    combo.paste(s, (t.width, 0))
    p = OUT / "combo_init.png"
    combo.save(p, optimize=True)
    b64 = base64.b64encode(p.read_bytes()).decode()
    (OUT / "combo_init.b64").write_text(b64)
    meta["combo"] = {"size": combo.size, "png_bytes": p.stat().st_size, "b64_chars": len(b64)}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))


def slice_result(name: str, result: Path, out_dir: Path) -> None:
    big = Image.open(result).convert("RGB")
    parts = [name] if name != "combo" else ["terrain", "sprites"]
    x_off = 0
    for part in parts:
        names, n, gutter = GRIDS[part]
        canvas, alphas, cell = build_grid(SRC, names, n, gutter, 1)
        region = big.crop((x_off, 0, x_off + canvas.width, canvas.height))
        if region.size != canvas.size:
            raise SystemExit(f"result region {region.size} != init {canvas.size}")
        for tile_name, tile in slice_grid(region, names, alphas, n, cell, gutter, 1).items():
            dest = out_dir / f"{tile_name}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            tile.save(dest)
        x_off += canvas.width
        print(f"{part}: {len(set(names))} tiles -> {out_dir}")


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        slice_result(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
