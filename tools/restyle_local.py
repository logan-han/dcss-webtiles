#!/usr/bin/env python3
"""Restyle DCSS 32x32 tiles locally with SDXL img2img + Pixel Art XL LoRA + LCM LoRA.

Each tile: 16x nearest upscale to 512, img2img at the given strength, k-centroid
downscale back to 32x32, then the original alpha mask is re-applied so the
silhouette is unchanged.

Pilot:
  python tools/restyle_local.py --src pilot/src --out pilot/out --strengths 0.35 0.5 0.65
Non-model parts only (facelift column, sanity checks):
  python tools/restyle_local.py --src pilot/src --out pilot/out --no-model
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

TILE = 32
SCALE = 16
BASE = "stabilityai/stable-diffusion-xl-base-1.0"
VAE = "madebyollin/sdxl-vae-fp16-fix"
PIXEL_LORA = ("nerijs/pixel-art-xl", "pixel-art-xl.safetensors")
LCM_LORA = "latent-consistency/lcm-lora-sdxl"
SPRITE_BG = (36, 36, 36)

PROMPTS = {
    "floor": "pixel art dungeon floor tile, top-down view, seamless stone and dirt ground texture, "
             "clean pixel clusters, subtle shading, muted fantasy palette",
    "wall": "pixel art dungeon wall tile, stone brick wall texture with defined mortar lines, "
            "clean pixel clusters, subtle shading, muted fantasy palette",
    "feature": "pixel art dungeon feature, top-down roguelike game tile, crisp readable shape, "
               "clean pixel clusters, dark outline, muted fantasy palette",
    "monster": "pixel art fantasy monster sprite, roguelike game character, bold silhouette, "
               "clean pixel clusters, dark outline, vivid readable colours, plain flat dark background",
    "item": "pixel art fantasy item icon, roguelike game object, crisp readable shape, "
            "clean pixel clusters, dark outline, plain flat dark background",
    "player": "pixel art fantasy adventurer sprite, roguelike game character, front view, bold silhouette, "
              "clean pixel clusters, dark outline, plain flat dark background",
}
NEGATIVE = "blurry, smooth gradients, photorealistic, 3d render, noise, text, watermark, jpeg artifacts"


def category(rel: str) -> str:
    p = rel.replace("\\", "/")
    if p.startswith("dngn/floor/"):
        return "floor"
    if p.startswith("dngn/wall/"):
        return "wall"
    if p.startswith("dngn/"):
        return "feature"
    if p.startswith("mon/"):
        return "monster"
    if p.startswith("item/"):
        return "item"
    if p.startswith("player/"):
        return "player"
    return "feature"


def prepare_init(tile: Image.Image, scale: int = SCALE) -> tuple[Image.Image, np.ndarray, bool]:
    rgba = tile.convert("RGBA")
    alpha = np.array(rgba)[:, :, 3]
    transparent = bool((alpha < 255).any())
    if transparent:
        bg = Image.new("RGBA", rgba.size, SPRITE_BG + (255,))
        flat = Image.alpha_composite(bg, rgba).convert("RGB")
    else:
        flat = rgba.convert("RGB")
    init = flat.resize((TILE * scale, TILE * scale), Image.NEAREST)
    return init, alpha, transparent


def kcentroid(img: Image.Image, size: int = TILE, iters: int = 8) -> Image.Image:
    """Astropulse-style k-centroid downscale: per block, 2-means, keep the dominant centroid."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape
    bh, bw = h // size, w // size
    blocks = a.reshape(size, bh, size, bw, 3).transpose(0, 2, 1, 3, 4).reshape(size * size, bh * bw, 3)
    lum = blocks @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    idx = np.arange(blocks.shape[0])
    c0 = blocks[idx, lum.argmin(1)]
    c1 = blocks[idx, lum.argmax(1)]
    n0 = n1 = None
    for _ in range(iters):
        d0 = ((blocks - c0[:, None]) ** 2).sum(-1)
        d1 = ((blocks - c1[:, None]) ** 2).sum(-1)
        m = d1 < d0
        n1 = m.sum(1, keepdims=True)
        n0 = (~m).sum(1, keepdims=True)
        c1n = (blocks * m[..., None]).sum(1) / np.maximum(n1, 1)
        c0n = (blocks * (~m)[..., None]).sum(1) / np.maximum(n0, 1)
        c1 = np.where(n1 > 0, c1n, c1)
        c0 = np.where(n0 > 0, c0n, c0)
    pick = np.where(n1 > n0, c1, c0)
    out = np.clip(np.rint(pick.reshape(size, size, 3)), 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def remask(rgb: Image.Image, alpha: np.ndarray, transparent: bool) -> Image.Image:
    if not transparent:
        return rgb.convert("RGBA")
    arr = np.dstack([np.asarray(rgb.convert("RGB")), alpha]).astype(np.uint8)
    arr[alpha == 0, :3] = 0
    return Image.fromarray(arr, "RGBA")


def facelift(tile: Image.Image, colors: int = 16) -> Image.Image:
    """No-AI baseline: saturation and contrast nudge, then a tight palette."""
    rgba = tile.convert("RGBA")
    arr = np.array(rgba)
    alpha = arr[:, :, 3]
    transparent = bool((alpha < 255).any())
    rgb_arr = arr[:, :, :3].copy()
    if transparent and (alpha > 0).any():
        fill = np.median(rgb_arr[alpha > 0], axis=0).astype(np.uint8)
        rgb_arr[alpha == 0] = fill
    rgb = Image.fromarray(rgb_arr, "RGB")
    rgb = ImageEnhance.Color(rgb).enhance(1.15)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.10)
    q = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    return remask(q, alpha, transparent)


def load_pipe(lora_weight: float = 1.2):
    import torch
    from diffusers import AutoencoderKL, LCMScheduler, StableDiffusionXLImg2ImgPipeline

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    vae = AutoencoderKL.from_pretrained(VAE, torch_dtype=torch.float16)
    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        BASE, vae=vae, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
    pipe.load_lora_weights(PIXEL_LORA[0], weight_name=PIXEL_LORA[1], adapter_name="pixel")
    pipe.load_lora_weights(LCM_LORA, adapter_name="lcm")
    pipe.set_adapters(["pixel", "lcm"], adapter_weights=[lora_weight, 1.0])
    pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    return pipe, device


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="pilot/src")
    ap.add_argument("--out", default="pilot/out")
    ap.add_argument("--strengths", nargs="*", type=float, default=[0.35, 0.5, 0.65])
    ap.add_argument("--steps", type=int, default=8, help="denoising steps actually run at each strength")
    ap.add_argument("--guidance", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=int, default=SCALE, help="upscale factor: 16 -> 512px, 32 -> 1024px (SDXL native)")
    ap.add_argument("--no-model", action="store_true", help="only write the facelift column")
    ap.add_argument("--prompt-suffix", default="", help="appended to every category prompt")
    ap.add_argument("--lora-weight", type=float, default=1.2, help="Pixel Art XL adapter weight")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    tiles = sorted(p for p in src.rglob("*.png"))
    if not tiles:
        raise SystemExit(f"no PNGs under {src}")

    for p in tiles:
        rel = p.relative_to(src)
        dest = out / "facelift" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        facelift(Image.open(p)).save(dest)
    print(f"facelift: {len(tiles)} tiles")
    if args.no_model:
        return

    import torch

    t0 = time.perf_counter()
    pipe, device = load_pipe(args.lora_weight)
    print(f"pipeline loaded on {device} in {time.perf_counter() - t0:.1f}s", flush=True)

    timings: list[dict] = []
    for p in tiles:
        rel = p.relative_to(src)
        cat = category(str(rel))
        init, alpha, transparent = prepare_init(Image.open(p), args.scale)
        for s in args.strengths:
            steps_total = max(args.steps, math.ceil(args.steps / s))
            gen = torch.Generator("cpu").manual_seed(args.seed)
            t1 = time.perf_counter()
            img = pipe(
                prompt=PROMPTS[cat] + (", " + args.prompt_suffix if args.prompt_suffix else ""),
                negative_prompt=NEGATIVE,
                image=init,
                strength=s,
                num_inference_steps=steps_total,
                guidance_scale=args.guidance,
                generator=gen,
            ).images[0]
            dt = time.perf_counter() - t1
            big = out / f"big{args.scale}" / f"{s}" / rel
            big.parent.mkdir(parents=True, exist_ok=True)
            img.save(big)
            final = remask(kcentroid(img), alpha, transparent)
            dest = out / f"{s}" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            final.save(dest)
            timings.append({"tile": str(rel), "category": cat, "strength": s, "steps_run": int(steps_total * s), "seconds": round(dt, 2)})
            print(f"{rel} s={s} steps={int(steps_total * s)} {dt:.1f}s", flush=True)

    (out / "timings.json").write_text(json.dumps(timings, indent=1))
    secs = [t["seconds"] for t in timings]
    print(f"{len(secs)} images, first {secs[0]:.1f}s, median {sorted(secs)[len(secs) // 2]:.1f}s, total {sum(secs):.0f}s")


if __name__ == "__main__":
    main()
