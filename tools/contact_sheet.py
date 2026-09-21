#!/usr/bin/env python3
"""Before/after contact sheet and a mock room for the pilot tiles.

  python tools/contact_sheet.py --src pilot/src --out pilot/out --variants facelift 0.35 0.5 0.65
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TILE = 32
ZOOM = 8
ROOM_ZOOM = 4
LABEL_W = 250
HEADER_H = 34
PAD = 6
FLOOR = "dngn/floor/grey_dirt0.png"


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def label(v: str) -> str:
    return v.split("=", 1)[0]


def load(p: Path) -> Image.Image | None:
    return Image.open(p).convert("RGBA") if p.exists() else None


def variant_tile(src: Path, out: Path, variant: str, rel: str) -> Image.Image | None:
    """variant is 'original', '<name>' under --out, or '<dir>:<name>' to read from another out dir."""
    if "=" in variant:
        variant = variant.split("=", 1)[1]
    if variant == "original":
        return load(src / rel)
    if ":" in variant:
        d, v = variant.split(":", 1)
        return load(Path(d) / v / rel)
    return load(out / variant / rel)


def sheet(src: Path, out: Path, variants: list[str], dest: Path, rows_from: Path | None = None) -> None:
    base = rows_from or src
    rels = sorted(str(p.relative_to(base)) for p in base.rglob("*.png"))
    cols = ["original"] + variants
    cell = TILE * ZOOM
    w = LABEL_W + len(cols) * (cell + PAD)
    h = HEADER_H + len(rels) * (cell + PAD)
    im = Image.new("RGBA", (w, h), (24, 24, 24, 255))
    d = ImageDraw.Draw(im)
    f = font(18)
    for ci, c in enumerate(cols):
        d.text((LABEL_W + ci * (cell + PAD) + 4, 8), label(c), fill=(230, 230, 230, 255), font=f)
    floor = load(src / FLOOR)
    for ri, rel in enumerate(rels):
        y = HEADER_H + ri * (cell + PAD)
        d.text((6, y + cell // 2 - 9), rel.replace(".png", ""), fill=(200, 200, 200, 255), font=f)
        for ci, c in enumerate(cols):
            x = LABEL_W + ci * (cell + PAD)
            t = variant_tile(src, out, c, rel)
            if t is None:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], outline=(200, 60, 60, 255), width=3)
                d.line([x, y, x + cell, y + cell], fill=(200, 60, 60, 255), width=3)
                continue
            base = floor.copy() if floor is not None else Image.new("RGBA", (TILE, TILE), (60, 60, 60, 255))
            comp = Image.alpha_composite(base, t)
            im.paste(comp.resize((cell, cell), Image.NEAREST), (x, y))
    im.save(dest)
    print(dest)


ROOM = [
    "WWWDWWW",
    "W>....W",
    "W..o..W",
    "W.J.@.W",
    "W~~..!W",
    "W~..S/W",
    "WWWWWWW",
]
GLYPHS = {
    "W": ["dngn/wall/brick_brown0.png"],
    ".": ["dngn/floor/grey_dirt0.png"],
    "D": ["dngn/floor/grey_dirt0.png", "dngn/doors/closed_door.png"],
    ">": ["dngn/floor/grey_dirt0.png", "dngn/gateways/stone_stairs_down.png"],
    "~": ["dngn/water/shallow_water.png"],
    "o": ["dngn/floor/grey_dirt0.png", "mon/humanoids/ogre.png"],
    "J": ["dngn/floor/grey_dirt0.png", "mon/animals/jackal.png"],
    "S": ["dngn/floor/grey_dirt0.png", "mon/unique/sigmund.png"],
    "@": ["dngn/floor/grey_dirt0.png", "player/base/human_m.png"],
    "!": ["dngn/floor/grey_dirt0.png", "item/potion/ruby.png"],
    "/": ["dngn/floor/grey_dirt0.png", "item/weapon/long_sword1.png"],
}


def room(src: Path, out: Path, variants: list[str], dest: Path) -> None:
    cols = ["original"] + variants
    rw, rh = len(ROOM[0]) * TILE, len(ROOM) * TILE
    panel_w = rw * ROOM_ZOOM
    w = len(cols) * (panel_w + PAD * 2)
    h = HEADER_H + rh * ROOM_ZOOM + PAD
    im = Image.new("RGBA", (w, h), (24, 24, 24, 255))
    d = ImageDraw.Draw(im)
    f = font(18)
    for ci, c in enumerate(cols):
        x0 = ci * (panel_w + PAD * 2) + PAD
        d.text((x0, 8), label(c), fill=(230, 230, 230, 255), font=f)
        panel = Image.new("RGBA", (rw, rh), (0, 0, 0, 255))
        for ry, row in enumerate(ROOM):
            for rx, g in enumerate(row):
                for layer in GLYPHS[g]:
                    t = variant_tile(src, out, c, layer) or load(src / layer)
                    if t is None:
                        continue
                    panel.alpha_composite(t, (rx * TILE, ry * TILE))
        im.paste(panel.resize((panel_w, rh * ROOM_ZOOM), Image.NEAREST), (x0, HEADER_H))
    im.save(dest)
    print(dest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="pilot/src")
    ap.add_argument("--out", default="pilot/out")
    ap.add_argument("--variants", nargs="*", default=["facelift", "0.35", "0.5", "0.65"])
    ap.add_argument("--sheet", default="pilot/contact_sheet.png")
    ap.add_argument("--room", default="pilot/room.png")
    ap.add_argument("--rows-from", default=None, help="only tiles present under this dir become rows")
    args = ap.parse_args()
    sheet(Path(args.src), Path(args.out), args.variants, Path(args.sheet), Path(args.rows_from) if args.rows_from else None)
    room(Path(args.src), Path(args.out), args.variants, Path(args.room))


if __name__ == "__main__":
    main()
