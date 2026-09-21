#!/usr/bin/env python3
"""Grid experiment: pack tiles into one SDXL canvas at 8x so the model's pixel size matches the tile grid.

  python tools/grid_pilot.py --out pilot/outgrid --strengths 0.35 0.5
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from restyle_local import NEGATIVE, SPRITE_BG, TILE, kcentroid, load_pipe, remask  # noqa: E402

TERRAIN = [
    "dngn/floor/grey_dirt0", "dngn/floor/lair0", "dngn/floor/pebble_brown0", "dngn/wall/brick_brown0",
    "dngn/wall/catacombs0", "dngn/wall/stone_gray0", "dngn/doors/closed_door", "dngn/gateways/stone_stairs_down",
    "dngn/water/shallow_water", "dngn/floor/grey_dirt0", "dngn/floor/lair0", "dngn/floor/pebble_brown0",
    "dngn/wall/brick_brown0", "dngn/wall/catacombs0", "dngn/wall/stone_gray0", "dngn/water/shallow_water",
]
SPRITES = [
    "item/potion/ruby", "item/weapon/long_sword1", "mon/animals/jackal", "mon/humanoids/ogre",
    "mon/unique/sigmund", "player/base/human_m", "mon/animals/jackal", "mon/humanoids/ogre", "item/potion/ruby",
]
PROMPT_TERRAIN = ("pixel art tileset of dungeon floor and wall tiles, top-down roguelike, 32x32 tiles, "
                  "clean pixel clusters, subtle shading, muted fantasy palette, seamless textures")
PROMPT_SPRITES = ("pixel art sprite sheet of fantasy roguelike monsters, adventurers and items, 32x32 sprites "
                  "on a plain dark background, bold silhouettes, dark outlines, clean pixel clusters, vivid readable colours")


def build_grid(src: Path, names: list[str], n: int, gutter: int, scale: int):
    cell = TILE + gutter
    canvas = Image.new("RGB", (n * cell, n * cell), SPRITE_BG)
    alphas = []
    for i, name in enumerate(names):
        rgba = Image.open(src / f"{name}.png").convert("RGBA")
        alpha = np.array(rgba)[:, :, 3]
        transparent = bool((alpha < 255).any())
        flat = Image.alpha_composite(Image.new("RGBA", rgba.size, SPRITE_BG + (255,)), rgba).convert("RGB")
        x, y = (i % n) * cell + gutter // 2, (i // n) * cell + gutter // 2
        canvas.paste(flat, (x, y))
        alphas.append((alpha, transparent))
    return canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST), alphas, cell


def slice_grid(big: Image.Image, names: list[str], alphas, n: int, cell: int, gutter: int, scale: int):
    outs = {}
    for i, name in enumerate(names):
        if name in outs:
            continue
        x, y = ((i % n) * cell + gutter // 2) * scale, ((i // n) * cell + gutter // 2) * scale
        crop = big.crop((x, y, x + TILE * scale, y + TILE * scale))
        alpha, transparent = alphas[i]
        outs[name] = remask(kcentroid(crop), alpha, transparent)
    return outs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="pilot/src")
    ap.add_argument("--out", default="pilot/outgrid")
    ap.add_argument("--strengths", nargs="*", type=float, default=[0.35, 0.5])
    ap.add_argument("--scale", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    import torch

    pipe, device = load_pipe()
    src, out = Path(args.src), Path(args.out)
    jobs = [("terrain", TERRAIN, 4, 0, PROMPT_TERRAIN), ("sprites", SPRITES, 3, 8, PROMPT_SPRITES)]
    for label, names, n, gutter, prompt in jobs:
        canvas, alphas, cell = build_grid(src, names, n, gutter, args.scale)
        (out / "canvas").mkdir(parents=True, exist_ok=True)
        canvas.save(out / "canvas" / f"{label}_init.png")
        for s in args.strengths:
            steps_total = max(8, math.ceil(8 / s))
            t0 = time.perf_counter()
            big = pipe(prompt=prompt, negative_prompt=NEGATIVE, image=canvas, strength=s,
                       num_inference_steps=steps_total, guidance_scale=1.5,
                       generator=torch.Generator("cpu").manual_seed(args.seed)).images[0]
            dt = time.perf_counter() - t0
            big.save(out / "canvas" / f"{label}_{s}.png")
            for name, tile in slice_grid(big, names, alphas, n, cell, gutter, args.scale).items():
                dest = out / f"{s}" / f"{name}.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                tile.save(dest)
            print(f"{label} {canvas.size} s={s} {dt:.1f}s ({len(set(names))} tiles)", flush=True)


if __name__ == "__main__":
    main()
