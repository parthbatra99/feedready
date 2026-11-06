from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from detect import MissingCapability, Scene, bootstrap_hint, main_faces
from portable import body_box
from imaging import cv2, gaussian, guided_filter, luma, resize, rgb_to_hsv, skin_mask, smoothstep

COMBINATORS = ("union", "intersect", "subtract")
MODIFIER_MAX = {"grow": 0.05, "feather": 0.05, "soft": 0.05}
PEOPLE_REACH = 0.03
SKIN_HUE_TOL = (8, 20)
SKIN_SMOOTH = 0.012


def build(spec: dict | None, scene: Scene) -> np.ndarray | None:
    if spec is None or spec.get("type") == "all":
        return None
    m = _base(spec, scene)
    return _modifiers(m, spec, scene)


def _base(spec: dict, scene: Scene) -> np.ndarray:
    img = scene.img
    H, W = img.shape[:2]
    S = min(H, W)
    op = spec.get("op")
    if op in COMBINATORS:
        parts = [build(s, scene) for s in spec["masks"]]
        parts = [np.ones((H, W), np.float32) if p is None else p for p in parts]
        out = parts[0]
        for p in parts[1:]:
            out = np.maximum(out, p) if op == "union" else np.minimum(out, p) if op == "intersect" else out * (1 - p)
        return out

    kind = spec.get("type")
    yy, xx = np.arange(H, dtype=np.float32)[:, None], np.arange(W, dtype=np.float32)[None, :]

    if kind == "radial":
        cx, cy = spec["center"]
        r = spec.get("radius", 0.2)
        rx, ry = (r, r) if np.isscalar(r) else r
        ang = np.deg2rad(spec.get("angle", 0))
        dx, dy = xx - cx * W, yy - cy * H
        u = (dx * np.cos(ang) + dy * np.sin(ang)) / (rx * S)
        v = (-dx * np.sin(ang) + dy * np.cos(ang)) / (ry * S)
        d = np.sqrt(u * u + v * v)
        f = spec.get("falloff", 0.5)
        return (1 - smoothstep(1 - f, 1, d)).astype(np.float32)

    if kind == "linear":
        (x0, y0), (x1, y1) = spec["start"], spec["end"]
        vx, vy = (x1 - x0) * W, (y1 - y0) * H
        t = ((xx - x0 * W) * vx + (yy - y0 * H) * vy) / max(vx * vx + vy * vy, 1e-6)
        return (1 - smoothstep(0, 1, t)).astype(np.float32)

    if kind in ("polygon", "brush"):
        canvas = Image.new("L", (W, H), 0)
        draw = ImageDraw.Draw(canvas)
        if kind == "polygon":
            draw.polygon([(x * W, y * H) for x, y in spec["points"]], fill=255)
        else:
            for dot in spec["dots"]:
                x, y = dot[0] * W, dot[1] * H
                r = (dot[2] if len(dot) > 2 else spec.get("size", 0.02)) * S
                draw.ellipse([x - r, y - r, x + r, y + r], fill=255)
        m = np.asarray(canvas, np.float32) / 255
        default_soft = 0.004 if kind == "polygon" else 0.006
        return gaussian(m, spec.get("soft", default_soft) * S)

    if kind == "luminance":
        return _band(luma(img), spec.get("min", 0), spec.get("max", 1), spec.get("soft", 0.08))

    if kind == "color":
        h, s, _ = rgb_to_hsv(img)
        d = np.abs((h - spec["hue"] + 180) % 360 - 180)
        rng, soft = spec.get("range", 25), spec.get("soft", 15)
        m = 1 - smoothstep(rng, rng + soft, d)
        return (m * smoothstep(spec.get("min_sat", 0.08), spec.get("min_sat", 0.08) + 0.08, s)).astype(np.float32)

    if kind == "person" and "faces" in spec:
        return _people(spec["faces"], scene)
    if kind in ("person", "subject"):
        return scene.vision_mask(kind)
    if kind == "skin":
        return _skin(spec, scene)
    if kind == "background":
        return 1 - scene.vision_mask("subject")

    if kind == "face":
        return _face(spec, scene)

    if kind == "segment":
        classes = spec["class"] if isinstance(spec["class"], list) else [spec["class"]]
        out = np.zeros((H, W), np.float32)
        for c in classes:
            out = np.maximum(out, scene.segment_mask(c, refine=spec.get("edge_refine", True)))
        return out

    if kind == "object":
        return scene.object_mask(spec.get("box"), spec.get("points", []), spec.get("exclude", []))[0]

    if kind == "sky":
        return scene.segment_mask("sky")

    raise ValueError(f"unknown mask type '{kind}'")


def _band(x, lo, hi, soft):
    up = smoothstep(lo - soft, lo + soft, x) if lo > 0 else np.ones_like(x)
    down = 1 - smoothstep(hi - soft, hi + soft, x) if hi < 1 else np.ones_like(x)
    return (up * down).astype(np.float32)


def _face_indices(spec_faces, faces: list[dict], what: str) -> list[int]:
    if not faces:
        raise MissingCapability(f"{what}: no face found; place a radial mask from the grid instead")
    if spec_faces == "all":
        return main_faces(faces)
    wanted = spec_faces if isinstance(spec_faces, list) else [spec_faces]
    bad = [i for i in wanted if not isinstance(i, int) or not 0 <= i < len(faces)]
    if bad or not wanted:
        raise ValueError(f"{what}: face index {bad or wanted} is not one of 0–{len(faces) - 1} (see summary.faces)")
    return wanted


def _face(spec: dict, scene: Scene) -> np.ndarray:
    faces = scene.faces()
    picks = _face_indices(spec.get("index", 0), faces, "face mask")
    if "index" not in spec and len(main_faces(faces)) > 1:
        scene.notes.append(f"face mask without an index lights face 0 only; {len(main_faces(faces))} main faces "
                           "were found, so use \"index\": \"all\" or one step per face")
    out = np.zeros(scene.img.shape[:2], np.float32)
    for i in picks:
        out = np.maximum(out, _one_face(spec, scene, faces[i]))
    return out


def _one_face(spec: dict, scene: Scene, f: dict) -> np.ndarray:
    x0, y0, x1, y1 = f["box"]
    H, W = scene.img.shape[:2]
    S = min(H, W)
    bw, bh = (x1 - x0) * W, (y1 - y0) * H
    part = spec.get("part", "face")
    scale = spec.get("scale", 1.0)
    if part == "eyes":
        lp, rp = f.get("left_pupil"), f.get("right_pupil")
        ipd = abs(lp[0] - rp[0]) * W if lp and rp else 0
        if ipd > 0.25 * bw:
            cx, cy = (lp[0] + rp[0]) / 2, (lp[1] + rp[1]) / 2
            rx, ry = ipd * 1.0, ipd * 0.55
        else:
            cx, cy = (x0 + x1) / 2, y0 + (y1 - y0) * 0.3
            rx, ry = bw * 0.6, bh * 0.3
    else:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = bw * 0.65, bh * 0.75
    return _base({"type": "radial", "center": [cx, cy], "radius": [rx * scale / S, ry * scale / S],
                  "falloff": spec.get("falloff", 0.6)}, scene)


def _people(spec_faces, scene: Scene) -> np.ndarray:
    faces = scene.faces()
    picks = _face_indices(spec_faces, faces, "person mask")
    person = scene.vision_mask("person")
    H, W = person.shape
    S = min(H, W)
    others = [k for k in main_faces(faces) if k not in picks]
    keep = np.zeros((H, W), np.float32)
    if cv2 is not None:
        n, labels = cv2.connectedComponents((person > 0.5).astype(np.uint8))
        hit = lambda k: _component_at(labels, faces[k]["box"], W, H)
        shared = {c for c in map(hit, others) if c}
        for k in picks:
            c = hit(k)
            if c and c not in shared:
                keep = np.maximum(keep, (labels == c).astype(np.float32))
        todo = [k for k in picks if not hit(k) or hit(k) in shared]
    else:
        todo = picks
    direct = np.zeros((H, W), np.float32)
    if todo:
        notes = list(scene.notes)
        for k in todo:
            x0, y0, x1, y1 = faces[k]["box"]
            centre = [(x0 + x1) / 2, (y0 + y1) / 2]
            exclude = [[(faces[o]["box"][0] + faces[o]["box"][2]) / 2, (faces[o]["box"][1] + faces[o]["box"][3]) / 2]
                       for o in others]
            cut = scene.object_mask(box=body_box(faces[k]["box"]), points=[centre], exclude=exclude)[0]
            if person[min(H - 1, int(centre[1] * H)), min(W - 1, int(centre[0] * W))] < 0.5:
                direct = np.maximum(direct, cut)
            else:
                keep = np.maximum(keep, (cut > 0.5).astype(np.float32))
        scene.notes[:] = notes
    reach = max(1, int(PEOPLE_REACH * S))
    if cv2 is not None:
        keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1, 2 * reach + 1)))
    else:
        keep = (gaussian(keep, reach) > 0.05).astype(np.float32)
    return np.maximum(np.minimum(person, keep), direct).astype(np.float32)


def _component_at(labels: np.ndarray, box, W: int, H: int) -> int:
    x0, y0, x1, y1 = (int(box[0] * W), int(box[1] * H), int(np.ceil(box[2] * W)), int(np.ceil(box[3] * H)))
    patch = labels[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)].ravel()
    patch = patch[patch > 0]
    if patch.size < 0.2 * max(1, (x1 - x0) * (y1 - y0)):
        return 0
    return int(np.bincount(patch).argmax())


def _skin(spec: dict, scene: Scene) -> np.ndarray:
    img = scene.img
    H, W = img.shape[:2]
    faces = scene.faces()
    picks = _face_indices(spec.get("faces", "all"), faces, "skin mask")
    region = _people(picks, scene)
    h, s, v = rgb_to_hsv(img)
    samples = [skin_mask(img, faces[k]["box"]) for k in picks]
    sel = np.zeros((H, W), bool)
    for m in samples:
        if m is not None:
            sel |= m
    if sel.sum() < 50:
        raise MissingCapability("skin mask: no readable skin on the chosen faces (covered, too dark or profile); "
                                "use a face mask instead")
    rad = np.deg2rad(h[sel])
    hue = float(np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())))
    spread = float(np.rad2deg(np.sqrt(-2 * np.log(max(1e-6, np.hypot(np.sin(rad).mean(), np.cos(rad).mean()))))))
    tol = float(np.clip(2 * spread, *SKIN_HUE_TOL))
    lo_s, hi_s = np.percentile(s[sel], [5, 95])
    d = np.abs((h - hue + 180) % 360 - 180)
    tone = (1 - smoothstep(tol, tol + 10, d)) * smoothstep(lo_s * 0.6, lo_s, s) * (1 - smoothstep(hi_s, hi_s * 1.3 + 0.05, s))
    tone = tone * smoothstep(0.06, 0.12, v)
    soft = guided_filter(img, tone.astype(np.float32), max(3, int(SKIN_SMOOTH * min(H, W))), 1e-2).clip(0, 1)
    return np.minimum(smoothstep(0.25, 0.6, soft), region).astype(np.float32)


def lint(spec: dict | None, where: str) -> list[str]:
    if not isinstance(spec, dict):
        return []
    found = []
    for key, top in MODIFIER_MAX.items():
        val = spec.get(key)
        if isinstance(val, (int, float)) and abs(val) > top:
            found.append(f"{where}: {key} {val} is a fraction of the short side, so it smears the mask across "
                         f"{abs(val):.0%} of the photo; use 0.002–0.03")
    for part in spec.get("masks", []):
        found += lint(part, where)
    return found


def _modifiers(m: np.ndarray, spec: dict, scene: Scene) -> np.ndarray:
    H, W = m.shape
    S = min(H, W)
    if g := spec.get("grow"):
        r = max(1, int(abs(g) * S))
        if cv2 is not None:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            m = cv2.dilate(m, k) if g > 0 else cv2.erode(m, k)
        else:
            blurred = gaussian(m, r)
            m = smoothstep(0.1, 0.5, blurred) if g > 0 else smoothstep(0.5, 0.9, blurred)
    refine = spec.get("refine")
    if refine == "grabcut":
        m = _grabcut(m, scene.img)
    if refine in ("edges", "grabcut"):
        m = guided_filter(scene.img, m.astype(np.float32), max(3, int(S * 0.006)), 1e-4)
    if f := spec.get("feather"):
        m = gaussian(m, f * S)
    m = np.clip(m, 0, 1)
    if spec.get("invert"):
        m = 1 - m
    return (m * spec.get("strength", 1.0)).astype(np.float32)


def _grabcut(m: np.ndarray, img: np.ndarray) -> np.ndarray:
    if cv2 is None:
        raise MissingCapability(f"refine: grabcut needs opencv: {bootstrap_hint('opencv')}")
    H, W = m.shape
    scale = min(1.0, 1024 / max(H, W))
    w, h = max(1, int(W * scale)), max(1, int(H * scale))
    small = resize(m, w, h)
    bgr = cv2.cvtColor((resize(img, w, h).clip(0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    gc[small > 0.5] = cv2.GC_PR_FGD
    k = max(3, int(min(w, h) * 0.03))
    gc[cv2.erode((small > 0.5).astype(np.uint8), np.ones((k, k), np.uint8)) > 0] = cv2.GC_FGD
    gc[cv2.dilate((small > 0.5).astype(np.uint8), np.ones((k * 2, k * 2), np.uint8)) == 0] = cv2.GC_BGD
    if not (gc == cv2.GC_FGD).any() or not (gc == cv2.GC_BGD).any():
        return m
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, gc, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    out = np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.float32)
    return resize(out, W, H)
