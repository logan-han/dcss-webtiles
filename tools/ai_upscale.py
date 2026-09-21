#!/usr/bin/env python3
"""Upscale an image with an ESRGAN-family pixel-art model via spandrel (MPS if available).

  python tools/ai_upscale.py <model.pth> <in.png> <out.png> [--to-scale 2]
--to-scale downsamples a 4x model's output to the given scale with Lanczos.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import torch
from PIL import Image
from spandrel import ModelLoader


def upscale(model, img: Image.Image, device: str) -> Image.Image:
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    t = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(t)
    out = out.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    return Image.fromarray((out * 255).round().astype(np.uint8), "RGB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--to-scale", type=int, default=None)
    args = ap.parse_args()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = ModelLoader().load_from_file(args.model).eval().to(device)
    img = Image.open(args.inp)
    t0 = time.perf_counter()
    out = upscale(model, img, device)
    dt = time.perf_counter() - t0
    if args.to_scale and model.scale != args.to_scale:
        out = out.resize((img.width * args.to_scale, img.height * args.to_scale), Image.LANCZOS)
    out.save(args.out)
    print(f"{args.model}: scale {model.scale}, {img.size} -> {out.size} in {dt:.2f}s on {device}")


if __name__ == "__main__":
    main()
