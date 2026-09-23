#!/usr/bin/env python3
"""Make 2x tile sheets for high-DPI screens with xBR, one tile at a time so neighbours never bleed.

Reads the packed sheets and their tileinfo-*.js from a webtiles game_data/static directory and
writes <sheet>-2x.png files. Each tile region is copied onto a spaced canvas (transparent margins,
RGB under transparency inpainted from the nearest opaque pixels), the canvas is upscaled with
ffmpeg's xBR filter (RGB and alpha separately, because the filter drops alpha), and the regions are
placed back at doubled coordinates.

  python tools/hd_sheets.py <static_dir> <out_dir> [--scale 2] [--filter xbr]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SHEETS = ["floor", "wall", "feat", "main", "player", "icons", "gui"]
MARGIN = 4
TILE_RE = re.compile(r"\{w: (-?\d+), h: (-?\d+), ox: (-?\d+), oy: (-?\d+), sx: (\d+), sy: (\d+), ex: (\d+), ey: (\d+)\}")


def regions(tileinfo_js: Path) -> list[tuple[int, int, int, int]]:
    text = tileinfo_js.read_text()
    matches = list(TILE_RE.finditer(text))
    if not matches or len(matches) != text.count("{w:"):
        sys.exit(f"{tileinfo_js.name}: TILE_RE matched {len(matches)} of {text.count('{w:')} tile entries; has the format changed?")
    seen, out = set(), []
    for m in matches:
        _, _, _, _, sx, sy, ex, ey = (int(v) for v in m.groups())
        if ex <= sx or ey <= sy:
            continue
        key = (sx, sy, ex, ey)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def inpaint(rgb: np.ndarray, alpha: np.ndarray, iters: int = 6) -> np.ndarray:
    """Fill RGB under transparent pixels from opaque neighbours so xBR sees no garbage colours."""
    rgb = rgb.astype(np.float32)
    known = alpha > 0
    if known.all() or not known.any():
        return rgb.astype(np.uint8)
    mean = rgb[known].mean(axis=0)
    rgb[~known] = mean
    for _ in range(iters):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(rgb.shape[:2], dtype=np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                sh = np.roll(np.roll(rgb, dy, axis=0), dx, axis=1)
                kn = np.roll(np.roll(known, dy, axis=0), dx, axis=1)
                acc += sh * kn[..., None]
                cnt += kn
        fill = (~known) & (cnt > 0)
        rgb[fill] = acc[fill] / cnt[fill][:, None]
        known = known | fill
    return np.clip(rgb, 0, 255).astype(np.uint8)


def shelf_pack(sizes: list[tuple[int, int]], margin: int, max_w: int = 4096):
    """Simple row packer. Returns positions and canvas size."""
    x = y = row_h = 0
    pos = []
    for w, h in sizes:
        cw, ch = w + 2 * margin, h + 2 * margin
        if x + cw > max_w and x > 0:
            x, y, row_h = 0, y + row_h, 0
        pos.append((x + margin, y + margin))
        x += cw
        row_h = max(row_h, ch)
    return pos, (max_w if len(sizes) > 1 else x, y + row_h)


def ffmpeg_scale(img: Image.Image, scale: int, filt: str, tmp: Path, name: str) -> Image.Image:
    src, dst = tmp / f"{name}_in.png", tmp / f"{name}_out.png"
    img.save(src)
    vf = f"{filt}={scale}" if filt in ("xbr", "hqx") else filt
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", vf,
                    "-pix_fmt", "rgb24", str(dst)], check=True)
    return Image.open(dst).convert("RGB")


def process_sheet(static: Path, out: Path, name: str, scale: int, filt: str, tmp: Path) -> bool:
    png, js = static / f"{name}.png", static / f"tileinfo-{name}.js"
    if not png.exists() or not js.exists():
        print(f"{name}: skipped (missing sheet or tileinfo)")
        return False
    sheet = np.array(Image.open(png).convert("RGBA"))
    regs = regions(js)
    sizes = [(ex - sx, ey - sy) for sx, sy, ex, ey in regs]
    pos, (cw, ch) = shelf_pack(sizes, MARGIN)
    canvas = np.zeros((ch, cw, 4), dtype=np.uint8)
    for (sx, sy, ex, ey), (px, py) in zip(regs, pos):
        tile = sheet[sy:ey, sx:ex]
        tile = np.dstack([inpaint(tile[:, :, :3], tile[:, :, 3]), tile[:, :, 3]])
        canvas[py:py + ey - sy, px:px + ex - sx] = tile
    # margins: extend inpainted colour outwards so edges are not pulled towards black
    rgb_filled = inpaint(canvas[:, :, :3], canvas[:, :, 3], iters=MARGIN + 2)
    rgb_big = ffmpeg_scale(Image.fromarray(rgb_filled, "RGB"), scale, filt, tmp, name + "_rgb")
    a_big = ffmpeg_scale(Image.fromarray(np.repeat(canvas[:, :, 3:4], 3, axis=2), "RGB"), scale, filt, tmp, name + "_a")
    rgb_big, a_big = np.array(rgb_big), np.array(a_big)[:, :, 0]
    H, W = sheet.shape[:2]
    result = np.zeros((H * scale, W * scale, 4), dtype=np.uint8)
    for (sx, sy, ex, ey), (px, py) in zip(regs, pos):
        w, h = (ex - sx) * scale, (ey - sy) * scale
        X, Y = px * scale, py * scale
        result[sy * scale:sy * scale + h, sx * scale:sx * scale + w, :3] = rgb_big[Y:Y + h, X:X + w]
        result[sy * scale:sy * scale + h, sx * scale:sx * scale + w, 3] = a_big[Y:Y + h, X:X + w]
    result[result[:, :, 3] == 0, :3] = 0
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result, "RGBA").save(out / f"{name}-{scale}x.png", optimize=True)
    print(f"{name}: {len(regs)} regions, {W}x{H} -> {W * scale}x{H * scale}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("static")
    ap.add_argument("out")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--filter", default="xbr", choices=["xbr", "hqx", "super2xsai"])
    ap.add_argument("--sheets", nargs="*", default=SHEETS)
    args = ap.parse_args()
    static, out = Path(args.static), Path(args.out)
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name in args.sheets:
            done += process_sheet(static, out, name, args.scale, args.filter, Path(tmp))
    # the game.html patch switches every sheet to -2x on high-DPI screens, so a skipped sheet is a build error
    if done != len(args.sheets):
        sys.exit(f"only {done} of {len(args.sheets)} sheets processed")


if __name__ == "__main__":
    main()
