from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import review
from imaging import luma, rgb_to_hsv, srgb_to_linear, to_u8

MAX_PHOTOS = 12
TOO_MANY = ("That's more than I can edit well in one chat ({n} photos; the limit is 12). In Claude Cowork, attach the "
            "folder and I'll work through all of them, or pick the 12 that matter most here.")
DETECTED = {"sky", "person", "subject", "background", "segment", "luminance", "color", "all"}
PLACED = {"radial", "brush", "polygon", "object"}
STRENGTH = 0.6
EV_CAP, WB_CAP = 0.5, 25
NEUTRAL_SAT, NEUTRAL_SHARE = 0.25, 0.03
EV_OFF, WARM_OFF = 0.35, 0.25
TEMP_PER_STOP, TINT_PER_STOP = 0.70, -0.30


def too_many(n: int) -> str | None:
    return TOO_MANY.format(n=n) if n > MAX_PHOTOS else None


def _mask_kind(spec) -> str:
    if spec is None:
        return "detected"
    if "op" in spec:
        kinds = {_mask_kind(m) for m in spec.get("masks", [])}
        return "placed" if "placed" in kinds else "check" if "check" in kinds else "detected"
    kind = spec.get("type")
    if kind in PLACED:
        return "placed"
    if kind == "linear":
        return "check"
    if kind in ("face", "skin") and isinstance(spec.get("index", spec.get("faces", "all")), (int, list)):
        return "placed"
    if kind == "person" and "faces" in spec:
        return "placed"
    return "detected" if kind in DETECTED | {"face", "skin"} else "placed"


def split(recipe: dict) -> tuple[dict, list[str], list[str]]:
    carried = copy.deepcopy({k: v for k, v in recipe.items() if k not in ("steps", "crop", "label", "note")})
    carried["steps"], dropped, check = [], [], []
    for i, step in enumerate(recipe.get("steps", [])):
        name = step.get("name", f"step {i + 1}")
        kind = _mask_kind(step.get("mask"))
        if kind == "placed" or step.get("adjust", {}).get("heal"):
            dropped.append(name)
            continue
        if kind == "check":
            check.append(name)
        carried["steps"].append(copy.deepcopy(step))
    return carried, dropped, check


def crop_for(recipe: dict, findings: list[dict]) -> tuple[dict | None, str | None]:
    crop = recipe.get("crop") or {}
    aspect = crop.get("aspect") or {"instagram": "4:5", "linkedin": "1:1", "story": "9:16"}.get(recipe.get("preset"))
    if not aspect:
        return None, None
    target = {"4:5": "instagram", "1:1": "linkedin"}.get(aspect)
    for f in findings:
        if f.get("check") != "crop":
            continue
        if "crop" in f and target in f["crop"]:
            return dict(f["crop"][target]), None
        if "would cut the subject" in f.get("finding", ""):
            return {"aspect": aspect}, f["finding"]
    return {"aspect": aspect}, None


def _balance(img: np.ndarray) -> tuple[float, float | None, float | None]:
    img = np.clip(img, 0, 1).astype(np.float32)
    lin = srgb_to_linear(img)
    y = luma(lin)
    mid = (y > 0.02) & (y < 0.8)
    level = float(np.median(y[mid] if mid.sum() > 64 else y)) + 1e-4
    _, sat, _ = rgb_to_hsv(img)
    neutral = mid & (sat < NEUTRAL_SAT)
    if neutral.mean() < NEUTRAL_SHARE:
        return level, None, None
    r, g, b = (float(np.mean(lin[..., c][neutral])) + 1e-4 for c in range(3))
    return level, float(np.log2(r / b)), float(np.log2(g / np.sqrt(r * b)))


def match(hero: np.ndarray, target: np.ndarray, strength: float = STRENGTH) -> dict:
    yh, rb_h, g_h = _balance(hero)
    yt, rb_t, g_t = _balance(target)
    values = [("exposure", round(float(np.clip(np.log2(yh / yt) * strength, -EV_CAP, EV_CAP)), 2))]
    if rb_h is not None and rb_t is not None:
        values += [("temp", round(float(np.clip((rb_h - rb_t) / TEMP_PER_STOP * 100 * strength, -WB_CAP, WB_CAP)))),
                   ("tint", round(float(np.clip((g_h - g_t) / TINT_PER_STOP * 100 * strength, -WB_CAP, WB_CAP))))]
    return {k: v for k, v in values if abs(v) >= (0.05 if k == "exposure" else 2)}


def neutral_found(img: np.ndarray) -> bool:
    return _balance(img)[1] is not None


def consistency(images: list[np.ndarray]) -> list[dict]:
    stats = [_balance(im) for im in images]
    ev = np.log2([s[0] for s in stats])
    warm = [s[1] for s in stats]
    known = [w for w in warm if w is not None]
    ev_mid = float(np.median(ev))
    warm_mid = float(np.median(known)) if len(known) >= 2 else None
    out = []
    for e, w in zip(ev, warm):
        flags = []
        if e - ev_mid > EV_OFF:
            flags.append(f"brighter than the rest by {e - ev_mid:.1f} stops")
        elif ev_mid - e > EV_OFF:
            flags.append(f"darker than the rest by {ev_mid - e:.1f} stops")
        shift = None if w is None or warm_mid is None else round(float(w - warm_mid), 2)
        if shift is not None and shift > WARM_OFF:
            flags.append("its greys and whites run warmer than the rest")
        elif shift is not None and shift < -WARM_OFF:
            flags.append("its greys and whites run cooler than the rest")
        out.append({"brightness": round(float(e - ev_mid), 2), "warmth": shift, "flags": flags})
    return out


def sheet(tiles: list[tuple[str, np.ndarray, bool]], path: Path, icc: bytes | None = None, width: int = 1080) -> None:
    n = len(tiles)
    cols = 2 if n <= 4 else 3
    gap, pad = 12, 24
    cell = (width - 2 * pad - (cols - 1) * gap) // cols
    ims = [Image.fromarray(to_u8(img)) for _, img, _ in tiles]
    rows = [ims[i:i + cols] for i in range(0, n, cols)]
    heights = [max(round(cell * im.height / im.width) for im in row) for row in rows]
    label = review.font(22, bold=True)
    sheet_h = 2 * pad + sum(heights) + gap * (len(rows) - 1)
    out = Image.new("RGBA", (width, sheet_h), review.INK + (255,))
    d = ImageDraw.Draw(out)
    y = pad
    for r, (row, h) in enumerate(zip(rows, heights)):
        for c, im in enumerate(row):
            k = r * cols + c
            fit = review._fit(im, cell, h)
            x = pad + c * (cell + gap) + (cell - fit.width) // 2
            top = y + (h - fit.height) // 2
            out.alpha_composite(review._rounded(fit, 10), (x, top))
            name, _, flagged = tiles[k]
            review._pill(d, (x + 10, top + 10), name, label)
            if flagged:
                cx, cy = x + fit.width - 24, top + 24
                d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=review.ACCENT)
                d.text((cx, cy), "!", fill=review.INK, font=label, anchor="mm")
        y += h + gap
    out.convert("RGB").save(path, quality=88, icc_profile=icc)
