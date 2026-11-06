from __future__ import annotations

import base64
import html
import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from imaging import cv2, gaussian, luma, to_u8

INK = (24, 24, 27)
MUTED = (160, 160, 170)
ACCENT = (232, 163, 61)
COLORS = [(255, 94, 58), (52, 199, 89), (10, 132, 255), (255, 204, 0), (191, 90, 242), (100, 210, 255),
          (255, 55, 95), (172, 142, 104), (0, 199, 190), (94, 92, 230), (255, 159, 10), (142, 142, 147)]
LEVEL_FILL = {"none": 0.04, "subtle": 0.25, "clear": 0.6, "strong": 1.0}


def font(size: int, bold: bool = False):
    names = (("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "DejaVuSans-Bold.ttf") if bold else
             ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def thumb(img: np.ndarray, long_edge: int) -> Image.Image:
    im = Image.fromarray(to_u8(img))
    im.thumbnail((long_edge, long_edge), Image.LANCZOS)
    return im


def color(i: int):
    return COLORS[i % len(COLORS)]


def grid_image(img: np.ndarray, faces: list[dict], path: Path, icc: bytes | None = None) -> None:
    im = thumb(img, 1400).convert("RGB")
    W, H = im.size
    draw = ImageDraw.Draw(im, "RGBA")
    size = max(12, W // 60)
    f = font(size)
    for i in range(1, 10):
        x, y = W * i / 10, H * i / 10
        width = 2 if i == 5 else 1
        draw.line([(x, 0), (x, H)], fill=(255, 255, 0, 150), width=width)
        draw.line([(0, y), (W, y)], fill=(255, 255, 0, 150), width=width)
        draw.text((x + 3, 3), f".{i}", fill=(255, 255, 0, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0, 255))
        draw.text((3, y + 2), f".{i}", fill=(255, 255, 0, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0, 255))
    for i, face in enumerate(faces):
        x0, y0, x1, y1 = face["box"]
        draw.rectangle([x0 * W, y0 * H, x1 * W, y1 * H], outline=(0, 255, 255, 255), width=2)
        draw.text((x0 * W + 2, max(0, y0 * H - size - 4)), str(i), fill=(0, 255, 255, 255), font=f,
                  stroke_width=2, stroke_fill=(0, 0, 0, 255))
    im.save(path, quality=90, icc_profile=icc)


def mask_sheet(img: np.ndarray, steps: list[dict], built: list, path: Path, icc: bytes | None = None) -> None:
    tiles = []
    f = font(22)
    for i, (step, m) in enumerate(zip(steps, built)):
        base = img.copy()
        if m is not None:
            base = base * (1 - 0.6 * m[..., None]) + np.array([1.0, 0.1, 0.1]) * 0.6 * m[..., None]
        tile = thumb(base, 520)
        ImageDraw.Draw(tile).text((8, 6), f"{i + 1}. {step.get('name', '')}"[:40], fill="white", font=f,
                                  stroke_width=3, stroke_fill="black")
        tiles.append(tile)
    cols = min(3, len(tiles))
    rows = -(-len(tiles) // cols)
    tw, th = tiles[0].size
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * 6, rows * th + (rows - 1) * 6), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (tw + 6), (i // cols) * (th + 6)))
    sheet.save(path, quality=88, icc_profile=icc)


def pair(left: np.ndarray, right: np.ndarray, labels: tuple[str, str], path: Path, icc: bytes | None = None,
         height: int = 900) -> None:
    a, b = thumb(left, 4000), thumb(right, 4000)
    a = a.resize((int(a.width * height / a.height), height), Image.LANCZOS)
    b = b.resize((int(b.width * height / b.height), height), Image.LANCZOS)
    sheet = Image.new("RGB", (a.width + b.width + 8, height), "white")
    sheet.paste(a, (0, 0))
    sheet.paste(b, (a.width + 8, 0))
    draw = ImageDraw.Draw(sheet)
    f = font(26)
    for x, label in ((10, labels[0]), (a.width + 18, labels[1])):
        draw.text((x, 8), label, fill="white", font=f, stroke_width=3, stroke_fill="black")
    sheet.save(path, quality=90, icc_profile=icc)


CARD_W, CARD_H, CARD_PAD = 1080, 1350, 40
PAPER = (237, 233, 226)
SOFT = (184, 178, 167)


def shape(w: int, h: int) -> str:
    r = w / h
    return "tall" if r < 0.65 else "portrait" if r <= 1.15 else "landscape"


def _fit(im: Image.Image, w: int, h: int) -> Image.Image:
    s = min(w / im.width, h / im.height)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)


def _rounded(im: Image.Image, r: int) -> Image.Image:
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], r, fill=255)
    out = Image.new("RGBA", im.size)
    out.paste(im.convert("RGB"), (0, 0), m)
    return out


def _pill(d: ImageDraw.ImageDraw, xy, text: str, f, ink=PAPER, anchor: str = "lt"):
    x, y = xy
    tw = int(d.textlength(text, font=f))
    th = getattr(f, "size", 16)
    pad_x, pad_y = th // 2, th // 3
    if anchor == "rt":
        x -= tw + 2 * pad_x
    d.rounded_rectangle([x, y, x + tw + 2 * pad_x, y + th + 2 * pad_y], th // 3, fill=(18, 17, 16, 200))
    d.text((x + pad_x, y + pad_y + th // 2), text, fill=ink, font=f, anchor="lm")


def round_card(before: np.ndarray, after: np.ndarray, tag: str, note: str, path: Path,
               icc: bytes | None = None, preview: bool = True) -> None:
    a, b = Image.fromarray(to_u8(after)), Image.fromarray(to_u8(before))
    kind = shape(a.width, a.height)
    sheet = Image.new("RGBA", (CARD_W, CARD_H), INK + (255,))
    d = ImageDraw.Draw(sheet)
    big, small = font(44, bold=True), font(22)
    inner = CARD_W - 2 * CARD_PAD
    lines = _wrap(d, note or tag, big, inner - 120)[:2]
    text_h = 40 + 56 * len(lines)
    area_h = CARD_H - 2 * CARD_PAD - text_h
    gap = 16
    label = f"{tag.upper()} · PREVIEW" if preview else f"{tag.upper()} · FULL QUALITY"
    if kind == "tall":
        bw, aw = _fit(b, (inner - gap) // 2, area_h), _fit(a, (inner - gap) // 2, area_h)
        y = CARD_PAD + (area_h - aw.height) // 2
        x = CARD_PAD + (inner - bw.width - gap - aw.width) // 2
        sheet.alpha_composite(_rounded(bw, 14), (x, y))
        sheet.alpha_composite(_rounded(aw, 14), (x + bw.width + gap, y))
        left = x
        _pill(d, (x + 16, y + 16), "BEFORE", small)
        _pill(d, (x + bw.width + gap + aw.width - 16, y + 16), label, small, ACCENT, "rt")
    elif kind == "portrait":
        aw = _fit(a, inner, area_h)
        x, y = CARD_PAD + (inner - aw.width) // 2, CARD_PAD + (area_h - aw.height) // 2
        sheet.alpha_composite(_rounded(aw, 16), (x, y))
        left = x
        inset = _fit(b, int(aw.width * 0.27), int(aw.height * 0.34))
        ix, iy = x + 24, y + aw.height - inset.height - 24
        d.rounded_rectangle([ix - 3, iy - 3, ix + inset.width + 2, iy + inset.height + 2], 12, fill=PAPER)
        sheet.alpha_composite(_rounded(inset, 10), (ix, iy))
        _pill(d, (ix, iy - 48), "BEFORE", small)
        _pill(d, (x + aw.width - 24, y + 24), label, small, ACCENT, "rt")
    else:
        half = (area_h - gap) // 2
        bw, aw = _fit(b, inner, half), _fit(a, inner, half)
        top = CARD_PAD + (area_h - bw.height - gap - aw.height) // 2
        bx, ax = CARD_PAD + (inner - bw.width) // 2, CARD_PAD + (inner - aw.width) // 2
        sheet.alpha_composite(_rounded(bw, 14), (bx, top))
        left = min(bx, ax)
        sheet.alpha_composite(_rounded(aw, 14), (ax, top + bw.height + gap))
        _pill(d, (bx + 16, top + 16), "BEFORE", small)
        _pill(d, (ax + aw.width - 16, top + bw.height + gap + 16), label, small, ACCENT, "rt")
    y = CARD_H - CARD_PAD - text_h + 40
    for line in lines:
        d.text((left, y), line, fill=PAPER, font=big)
        y += 56
    sheet.convert("RGB").save(path, quality=90, icc_profile=icc)


def detail_box(img: np.ndarray, faces: list[list[float]], side: int) -> tuple[tuple[int, int, int, int], str]:
    H, W = img.shape[:2]
    side = min(side, H, W)
    if faces:
        x0, y0, x1, y1 = max(faces, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        cx, cy, what = (x0 + x1) / 2 * W, (y0 + (y1 - y0) * 0.4) * H, "the face"
    else:
        g = luma(img[::4, ::4]) if img.shape[0] >= 64 else luma(img)
        step = 4 if img.shape[0] >= 64 else 1
        gy, gx = np.gradient(g)
        energy = gaussian(np.hypot(gx, gy).astype(np.float32), max(1.0, side / step / 6))
        y, x = np.unravel_index(int(energy.argmax()), energy.shape)
        cx, cy, what = x * step, y * step, "the most detailed patch"
    x = int(min(max(cx - side / 2, 0), W - side))
    y = int(min(max(cy - side / 2, 0), H - side))
    return (x, y, side, side), what


def describe(adjust: dict, look: str | None = None, amount: float | None = None) -> str:
    parts = []
    if look:
        parts.append(f"look {look}" + (f" {amount:g}%" if amount not in (None, 100) else ""))
    for k, v in adjust.items():
        if k == "hsl":
            parts.append("hsl " + " ".join(sorted(v)))
        elif k == "curve":
            parts.append("curve")
        elif isinstance(v, bool):
            parts.append(k)
        elif isinstance(v, (int, float)):
            parts.append(f"{k} {v:+g}")
    return ", ".join(parts) or "no change"


def _anchor(m: np.ndarray) -> tuple[int, int] | None:
    if cv2 is None:
        ys, xs = np.nonzero(m)
        return (int(xs.mean()), int(ys.mean())) if len(xs) else None
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n < 2:
        return None
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    region = np.pad((labels == big).astype(np.uint8), 1)
    dist = cv2.distanceTransform(region, cv2.DIST_L2, 5)[1:-1, 1:-1]
    y, x = np.unravel_index(int(dist.argmax()), dist.shape)
    return int(x), int(y)


def edit_map(img: np.ndarray, steps: list[dict], built: list, path: Path, icc: bytes | None = None,
             long_edge: int = 1000) -> None:
    base = thumb(img, long_edge).convert("RGBA")
    W, H = base.size
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(over)
    f, small = font(22), font(17)
    placed, whole = [], []
    for i, m in enumerate(built):
        col = color(i)
        if m is None or float(m.mean()) > 0.92:
            whole.append(i)
            continue
        small_m = Image.fromarray(to_u8(m)).resize((W, H), Image.BILINEAR)
        binary = (np.asarray(small_m) > 100).astype(np.uint8)
        if not binary.any():
            continue
        tint = np.zeros((H, W, 4), np.uint8)
        tint[..., :3] = col
        tint[..., 3] = (np.asarray(small_m).astype(np.float32) * 0.22).astype(np.uint8)
        over = Image.alpha_composite(over, Image.fromarray(tint, "RGBA"))
        draw = ImageDraw.Draw(over)
        if cv2 is not None:
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                if cv2.contourArea(c) < 30:
                    continue
                pts = [tuple(int(v) for v in p[0]) for p in c]
                draw.line(pts + [pts[0]], fill=col + (255,), width=3)
        if (pt := _anchor(binary)) is None:
            continue
        x, y = pt
        for px, py in placed:
            if abs(px - x) < 40 and abs(py - y) < 40:
                y += 44
        placed.append((x, y))
        draw.ellipse([x - 18, y - 18, x + 18, y + 18], fill=col + (255,), outline=(0, 0, 0, 255), width=2)
        draw.text((x, y), str(i + 1), fill="black", font=f, anchor="mm")
    if whole:
        text = "whole photo: " + "  ".join(f"{i + 1}. {steps[i].get('name', '')}" for i in whole)
        tw = int(draw.textlength(text, font=small))
        draw.rounded_rectangle([10, H - 44, 30 + tw, H - 10], 8, fill=(0, 0, 0, 180))
        draw.text((20, H - 27), text, fill="white", font=small, anchor="lm")
    Image.alpha_composite(base, over).convert("RGB").save(path, quality=90, icc_profile=icc)


def _lens(m: np.ndarray | None, W: int, H: int) -> tuple[int, int, int, int]:
    if m is None or float(m.mean()) > 0.5:
        return 0, 0, W, H
    ys, xs = np.nonzero(m > 0.3)
    if not len(xs):
        return 0, 0, W, H
    pad = int(0.08 * min(H, W))
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(W, xs.max() + pad), min(H, ys.max() + pad)
    side = max(x1 - x0, y1 - y0, int(0.25 * min(H, W)))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    x0, y0 = max(0, min(W - side, cx - side // 2)), max(0, min(H - side, cy - side // 2))
    return x0, y0, min(W, x0 + side), min(H, y0 + side)


def cards(before: np.ndarray, singles: list[dict], path: Path, icc: bytes | None = None, tile: int = 330) -> None:
    H, W = before.shape[:2]
    f, small = font(21), font(16)
    text_w = 420
    rows = []
    for c in sorted(singles, key=lambda c: -c["rank_score"]):
        x0, y0, x1, y1 = _lens(c["mask"], W, H)
        a = Image.fromarray(to_u8(before[y0:y1, x0:x1]))
        b = Image.fromarray(to_u8(c["after"][y0:y1, x0:x1]))
        a.thumbnail((tile, tile), Image.LANCZOS)
        b.thumbnail((tile, tile), Image.LANCZOS)
        row_h = max(a.height, 150) + 16
        row = Image.new("RGB", (a.width + b.width + 24 + text_w, row_h), INK)
        row.paste(a, (8, 8))
        row.paste(b, (16 + a.width, 8))
        d = ImageDraw.Draw(row)
        for x, label in ((12, "before"), (20 + a.width, "after")):
            d.text((x, 12), label, fill="white", font=small, stroke_width=2, stroke_fill="black")
        col = color(c["index"])
        tx = a.width + b.width + 34
        d.ellipse([tx, 10, tx + 34, 44], fill=col)
        d.text((tx + 17, 27), str(c["index"] + 1), fill="black", font=f, anchor="mm")
        d.text((tx + 46, 14), c["name"][:30], fill="white", font=f)
        y = 44
        if why := c.get("why"):
            for line in _wrap(d, why, small, text_w - 60)[:3]:
                d.text((tx + 46, y), line, fill=(220, 220, 228), font=small)
                y += 20
        d.text((tx + 46, y + 4), c["summary"][:52], fill=MUTED, font=small)
        d.text((tx + 46, y + 30), f"impact: {c['level']}", fill=col, font=small)
        d.rectangle([tx + 46, y + 54, tx + 46 + 220, y + 62], fill=(50, 50, 56))
        d.rectangle([tx + 46, y + 54, tx + 46 + int(220 * LEVEL_FILL[c["level"]]), y + 62], fill=col)
        rows.append(row)
    width = max(r.width for r in rows)
    sheet = Image.new("RGB", (width, sum(r.height for r in rows)), INK)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(path, quality=90, icc_profile=icc)


def _wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def board(tiles: list[tuple[str, str, np.ndarray]], path: Path, icc: bytes | None = None, edge: int = 640) -> None:
    ims = [thumb(img, edge) for _, _, img in tiles]
    portrait = sum(im.height > im.width * 1.15 for im in ims) > len(ims) / 2
    n = len(ims)
    cols = n if n <= 3 or (portrait and n <= 4) else 2 if n == 4 else 4 if portrait else 3
    cw, ch = max(im.width for im in ims), max(im.height for im in ims)
    caption = 74
    rows = -(-len(ims) // cols)
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * 10, rows * (ch + caption) + (rows + 1) * 10), INK)
    d = ImageDraw.Draw(sheet)
    big, small = font(26), font(16)
    for i, ((title, sub, _), im) in enumerate(zip(tiles, ims)):
        x = 10 + (i % cols) * (cw + 10)
        y = 10 + (i // cols) * (ch + caption + 10)
        sheet.paste(im, (x + (cw - im.width) // 2, y + (ch - im.height) // 2))
        d.text((x + 4, y + ch + 10), title[:34], fill="white", font=big)
        for j, line in enumerate(_wrap(d, sub, small, cw - 8)[:2]):
            d.text((x + 4, y + ch + 42 + j * 18), line, fill=MUTED, font=small)
    sheet.save(path, quality=88, icc_profile=icc)


def _uri(im: Image.Image, edge: int, quality: int = 84) -> str:
    im = im.convert("RGB")
    im.thumbnail((edge, edge), Image.LANCZOS)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _data_uri(path: Path, edge: int = 1400) -> str:
    return _uri(Image.open(path), edge)


def lens_pair(before: np.ndarray, after: np.ndarray, mask: np.ndarray | None, edge: int = 360) -> tuple[str, str]:
    H, W = before.shape[:2]
    x0, y0, x1, y1 = _lens(mask, W, H)
    return (_uri(Image.fromarray(to_u8(before[y0:y1, x0:x1])), edge, 80),
            _uri(Image.fromarray(to_u8(after[y0:y1, x0:x1])), edge, 80))


def hex_color(i: int) -> str:
    return "#%02x%02x%02x" % color(i)


FULL_VERSIONS = 6


def review_html(path: Path, title: str, versions: list[dict], *, subtitle: str = "", steps: list[dict] | None = None,
                edit_map: Path | None = None, board: Path | None = None, still_open: str | None = None,
                full_quality: bool = False) -> None:
    befores, entries = {}, []
    for k, v in enumerate(versions):
        key = str(v["before"])
        if key not in befores:
            befores[key] = _data_uri(v["before"])
        full = k >= len(versions) - FULL_VERSIONS
        entries.append({"n": v["n"], "note": v.get("note", ""), "after": _data_uri(v["after"], 1400 if full else 480),
                        "before": key})
    data = {"title": title, "subtitle": subtitle, "befores": befores, "versions": entries,
            "steps": steps or [], "map": _data_uri(edit_map, 1000) if edit_map and edit_map.exists() else None,
            "board": _data_uri(board, 1400) if board and board.exists() else None,
            "stillOpen": still_open, "fullQuality": full_quality}
    blob = json.dumps(data).replace("</", "<\\/")
    path.write_text(PAGE.replace("__TITLE__", html.escape(title)).replace("__DATA__", blob))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>__TITLE__</title>
<style>
:root{--bg:#121110;--panel:#1b1a18;--line:#2b2925;--ink:#ede9e2;--soft:#b8b2a7;--muted:#9c968c;--accent:#e8a33d;--ok:#8fc79a;--okbg:#1d2a1f;--warnbg:#2a2113}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-text-size-adjust:100%}
button{font:inherit;color:inherit}
.wrap{max-width:1320px;margin:0 auto;padding:16px 16px 40px;display:flex;flex-wrap:wrap;gap:20px 32px;align-items:flex-start}
header{flex:1 1 100%;display:flex;justify-content:space-between;align-items:center;gap:12px}
.eyebrow{font:12px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;color:var(--muted);text-transform:uppercase}
h1{margin:2px 0 0;font-size:21px;font-weight:600;letter-spacing:-.01em}
.badge{flex:none;padding:5px 10px;border-radius:999px;font-size:13px;background:var(--warnbg);color:var(--accent)}
.badge.ok{background:var(--okbg);color:var(--ok)}
main{flex:999 1 520px;min-width:0;display:flex;flex-direction:column;gap:14px}
aside{flex:1 1 400px;min-width:0;display:flex;flex-direction:column;gap:12px}
.stage{position:relative;margin:0 auto;width:fit-content;max-width:100%;border-radius:12px;overflow:hidden;background:#000;touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;cursor:pointer}
.stage img{display:block;max-width:100%;max-height:62vh;max-height:62svh;width:auto;height:auto}
.stage img.before{position:absolute;inset:0;width:100%;height:100%;max-height:none;clip-path:inset(0 calc(100% - var(--x,0%)) 0 0)}
.stage .tag{position:absolute;top:10px;right:10px;padding:4px 9px;border-radius:6px;background:rgba(18,17,16,.75);font:12px ui-monospace,Menlo,monospace;color:var(--accent);pointer-events:none}
.stage .hint{position:absolute;left:10px;bottom:10px;padding:5px 10px;border-radius:6px;background:rgba(18,17,16,.75);font-size:13px;pointer-events:none}
.stage .bar{position:absolute;top:0;bottom:0;left:var(--x,0%);width:2px;margin-left:-1px;background:var(--ink);display:none;pointer-events:none}
.stage.split .bar{display:block}
.stage input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:ew-resize;display:none}
.stage.split input{display:block}
.seg{display:flex;gap:4px;padding:4px;margin:0 auto;border:1px solid var(--line);border-radius:10px}
.seg button{min-height:36px;min-width:72px;padding:0 14px;border:0;border-radius:7px;background:transparent;color:var(--muted);cursor:pointer}
.seg button[aria-pressed=true]{background:var(--line);color:var(--ink)}
.note{margin:0;text-align:center;color:var(--soft)}
.open{margin:0;padding:10px 14px;border-radius:10px;background:var(--warnbg);color:var(--ink);font-size:14px}
.chips{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
.chips::-webkit-scrollbar{display:none}
.ver{flex:none;display:flex;align-items:center;gap:8px;padding:4px 12px 4px 4px;border-radius:8px;border:1px solid var(--line);background:var(--panel);cursor:pointer;min-height:44px}
.ver img{height:48px;width:auto;max-width:64px;object-fit:cover;border-radius:4px;display:block}
.ver span{font:13px ui-monospace,Menlo,monospace}
.ver[aria-pressed=true]{border-color:var(--accent)}
.small{font-size:13px;color:var(--muted)}
.reply{flex:none;min-height:44px;padding:0 16px;border-radius:999px;border:1px solid var(--line);background:var(--panel);cursor:pointer}
.primary{display:flex;align-items:center;justify-content:center;gap:10px;min-height:52px;border:0;border-radius:12px;background:var(--accent);color:#121110;font-weight:600;cursor:pointer;width:100%}
details{border:1px solid var(--line);border-radius:12px;background:var(--panel)}
summary{list-style:none;display:flex;justify-content:space-between;align-items:center;min-height:52px;padding:0 16px;cursor:pointer}
summary::-webkit-details-marker{display:none}
summary b{font-weight:500}
summary .act{color:var(--muted);font-size:14px}
details[open] summary .act::after{content:"Hide"}
details:not([open]) summary .act::after{content:"Show"}
.body{padding:0 12px 14px;display:flex;flex-direction:column;gap:12px}
.lead{display:flex;gap:12px;align-items:center}
.pair{flex:none;display:flex;gap:2px}
.pair img{width:76px;height:76px;object-fit:cover;display:block}
.pair img:first-child{border-radius:8px 0 0 8px}.pair img:last-child{border-radius:0 8px 8px 0}
.dot{flex:none;width:22px;height:22px;border-radius:50%;color:#121110;font-size:12px;font-weight:700;display:inline-flex;align-items:center;justify-content:center}
.name{font-weight:500}
.why{font-size:13px;color:var(--soft)}
.moves{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
.row{display:flex;align-items:center;gap:10px;min-height:40px;border-top:1px solid #22201d}
.row .name{flex:1 1 auto;font-weight:400;font-size:14px}
.label{font-size:12px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase}
.map{width:100%;border-radius:8px;display:block}
.hist{width:100%;border-radius:8px;display:block}
ol.notes{margin:0;padding-left:20px;color:var(--soft);font-size:14px}
.foot{margin:4px 0 0;font-size:13px;color:var(--muted)}
@media (min-width:1000px){.stage img{max-height:68vh;max-height:68svh}}
</style></head><body>
<div class="wrap">
<header><div><div class="eyebrow" id="eyebrow"></div><h1 id="title"></h1></div><span class="badge" id="badge"></span></header>
<main>
<div class="stage" id="stage" style="--x:0%">
<img class="after" id="after" alt=""><img class="before" id="before" alt="The photo as shot">
<div class="bar"></div><span class="tag" id="tag"></span><span class="hint" id="hint"></span>
<input type="range" min="0" max="100" value="50" id="split" aria-label="Before and after split">
</div>
<div class="seg" role="group" aria-label="Compare mode"><button id="mHold" aria-pressed="true">Hold</button><button id="mSplit" aria-pressed="false">Split</button></div>
<p class="note" id="note"></p>
<p class="open" id="open" hidden></p>
<div class="chips" id="vers" aria-label="Versions"></div>
<div><div class="small" id="replyHint">Say what to change in the chat, or tap one to copy it</div>
<div class="chips" id="replies" style="margin-top:8px"></div></div>
<button class="primary" id="export"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/></svg><span id="exportLabel">Export full quality</span></button>
</main>
<aside>
<details id="changes" hidden><summary><span><b>What changed</b> <span class="small" id="count"></span></span><span class="act"></span></summary><div class="body" id="changesBody"></div></details>
<details id="history" hidden><summary><span><b>How we got here</b> <span class="small" id="rounds"></span></span><span class="act"></span></summary><div class="body" id="historyBody"></div></details>
<p class="foot">Rendered on your device. Nothing uploaded.</p>
</aside>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const el=(tag,attrs,kids)=>{const e=document.createElement(tag);for(const k in attrs||{}){if(k==="text")e.textContent=attrs[k];else e.setAttribute(k,attrs[k])}for(const c of kids||[])e.appendChild(c);return e};
const stage=$("stage"),after=$("after"),before=$("before"),split=$("split");
let cur=D.versions.length-1,mode="hold",holding=false;
const latest=()=>D.versions[D.versions.length-1];
function setX(v){stage.style.setProperty("--x",v+"%")}
function paint(){
  const v=D.versions[cur];
  after.src=v.after;after.alt="v"+v.n+": "+(v.note||"");before.src=D.befores[v.before];
  const shown=mode==="hold"?(holding?100:0):+split.value;setX(shown);
  $("tag").textContent=mode==="hold"&&holding?"AS SHOT":"V"+v.n+(D.fullQuality?" · FULL QUALITY":" · PREVIEW");
  $("hint").textContent=mode==="split"?"Drag to compare":holding?"Original":"Press and hold for the original";
  $("note").textContent="v"+v.n+(v.note?" · "+v.note:"");
  [...$("vers").children].forEach((b,i)=>b.setAttribute("aria-pressed",i===cur));
  $("exportLabel").textContent=D.fullQuality?"Save v"+v.n+", already full size":"Export v"+v.n+" at full quality";
}
function setMode(m){mode=m;stage.classList.toggle("split",m==="split");$("mHold").setAttribute("aria-pressed",m==="hold");$("mSplit").setAttribute("aria-pressed",m==="split");if(m==="split")split.value=50;holding=false;paint()}
$("mHold").onclick=()=>setMode("hold");$("mSplit").onclick=()=>setMode("split");
split.oninput=paint;
const hold=on=>{if(mode!=="hold"||holding===on)return;holding=on;paint()};
stage.addEventListener("pointerdown",e=>{if(mode==="hold"){e.preventDefault();hold(true)}});
for(const ev of ["pointerup","pointerleave","pointercancel"])stage.addEventListener(ev,()=>hold(false));
stage.addEventListener("contextmenu",e=>{if(mode==="hold")e.preventDefault()});
addEventListener("keydown",e=>{if(e.key==="b"||e.key==="B")hold(true)});
addEventListener("keyup",e=>{if(e.key==="b"||e.key==="B")hold(false)});
D.versions.forEach((v,i)=>{const b=el("button",{class:"ver","aria-label":"v"+v.n+(v.note?": "+v.note:"")},[el("img",{src:v.after,alt:""}),el("span",{text:"v"+v.n})]);b.onclick=()=>{cur=i;paint()};$("vers").appendChild(b)});
function copy(t){try{navigator.clipboard.writeText(t)}catch(e){}$("replyHint").textContent="Copied “"+t+"”. Paste it in the chat."}
const replies=["looks done"];if(D.versions.length>1)replies.push("back to v"+D.versions[D.versions.length-2].n);replies.push("more","less","warmer","cooler");
replies.forEach(t=>{const b=el("button",{class:"reply",text:t});b.onclick=()=>copy(t);$("replies").appendChild(b)});
$("export").onclick=()=>copy("export v"+D.versions[cur].n);
$("eyebrow").textContent="Round "+latest().n+(D.subtitle?" · "+D.subtitle:"");
$("title").textContent=D.title;
const badge=$("badge");badge.textContent=D.stillOpen?"One fix left":D.fullQuality?"Full quality":"Your turn";if(!D.stillOpen&&D.fullQuality)badge.classList.add("ok");
if(D.stillOpen){$("open").hidden=false;$("open").textContent="I’d still change: "+D.stillOpen}
const level={none:0,subtle:1,clear:2,strong:3};
const meter=l=>{const s=el("span",{style:"flex:none;display:flex;gap:3px","aria-label":l+" impact"});for(let i=1;i<=3;i++)s.appendChild(el("span",{style:"width:10px;height:4px;border-radius:2px;background:"+(level[l]>=i?"var(--accent)":"var(--line)")}));return s};
if(D.steps.length){
  const box=$("changesBody");$("changes").hidden=false;$("count").textContent="· "+D.steps.length+(D.steps.length===1?" edit":" edits");
  const top=D.steps.slice(0,3),rest=D.steps.slice(3);
  box.appendChild(el("div",{class:"label",text:top.length<D.steps.length?"The ones that matter":"Each edit"}));
  for(const s of top){box.appendChild(el("div",{class:"lead"},[el("div",{class:"pair"},[el("img",{src:s.lensB,alt:"Before: "+s.name}),el("img",{src:s.lensA,alt:"After: "+s.name})]),el("div",{style:"min-width:0;display:flex;flex-direction:column;gap:2px"},[el("div",{style:"display:flex;align-items:center;gap:8px"},[el("span",{class:"dot",style:"background:"+s.color,text:String(s.n)}),el("span",{class:"name",text:s.name})]),el("span",{class:"why",text:s.why||""}),el("span",{class:"moves",text:s.summary||""})])]))}
  if(rest.length){box.appendChild(el("div",{class:"label",text:"And the smaller ones"}));const list=el("div");for(const s of rest)list.appendChild(el("div",{class:"row"},[el("span",{class:"dot",style:"background:"+s.color,text:String(s.n)}),el("span",{class:"name",text:s.name}),meter(s.level)]));box.appendChild(list)}
  if(D.map)box.appendChild(el("img",{class:"map",src:D.map,alt:"Where each edit lands, numbered"}));
}
if(D.versions.length>1||D.board){
  const box=$("historyBody");$("history").hidden=false;$("rounds").textContent="· "+D.versions.length+(D.versions.length===1?" round":" rounds");
  if(D.board)box.appendChild(el("img",{class:"hist",src:D.board,alt:"The directions board"}));
  const ol=el("ol",{class:"notes"});for(const v of D.versions)ol.appendChild(el("li",{text:"v"+v.n+(v.note?" · "+v.note:"")}));box.appendChild(ol);
}
const wide=matchMedia("(min-width: 1000px)");const fit=()=>{if(wide.matches)$("changes").open=true};fit();wide.addEventListener("change",fit);
paint();
</script></body></html>
"""
