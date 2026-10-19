from __future__ import annotations

import json

import numpy as np

import lib
import detect
from imaging import load_mask, resize

FACE_IOU = 0.7
PUPIL_MEDIAN = 0.01
PUPIL_MAX = 0.03
MASK_IOU = 0.8
MIN_SHARE = 0.05


def _box_iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _mask(path, shape):
    if not path.exists():
        return None
    m = load_mask(path)
    return (m if m.shape == shape else resize(m, shape[1], shape[0])) > 0.5


def _compare(src, faces, pupils, masks):
    import feedready

    with lib.isolated_work():
        work, working, img = feedready.prepare(src)
        apple = detect.Scene(work, working, img).vision()
        with lib.portable_tier():
            scene = detect.Scene(work, working, img)
            portable = scene.vision()
            portable_dir = scene.vision_dir()
    H, W = img.shape[:2]
    diag = float(np.hypot(W, H))
    for f in apple["faces"]:
        best = max(portable["faces"], key=lambda g: _box_iou(f["box"], g["box"]), default=None)
        if best is None or _box_iou(f["box"], best["box"]) < 0.3:
            faces.append(0.0)
            continue
        faces.append(_box_iou(f["box"], best["box"]))
        for key in ("left_pupil", "right_pupil"):
            if f.get(key):
                pupils.append(float(np.hypot((f[key][0] - best[key][0]) * W, (f[key][1] - best[key][1]) * H)) / diag)
    for name in ("person", "subject"):
        a, b = _mask(work / "vision" / f"{name}.png", (H, W)), _mask(portable_dir / f"{name}.png", (H, W))
        if a is None or a.mean() < MIN_SHARE:
            continue
        union = (a | b).sum() if b is not None else a.sum()
        masks[name].append(float((a & b).sum()) / union if b is not None else 0.0)
    keys = set(portable) - {"backend"}
    return keys <= set(apple) | {"person", "subject_instances"}


def run():
    if not detect.engine_available():
        lib.skip("portable vs Apple Vision", "needs the Mac engine to compare against")
        return
    if not detect.portable_vision_available():
        lib.skip("portable vs Apple Vision", "portable models missing: setup.sh --models --segformer")
        return
    photos = lib.corpus_photos(("kodak", "commons", "private"))
    if not photos:
        lib.skip("portable vs Apple Vision", "no corpus: selftest.py --fetch-corpus")
        return
    faces, pupils, masks, schema = [], [], {"person": [], "subject": []}, []
    for src in photos:
        schema.append(_compare(src, faces, pupils, masks))
    lib.check("portable vision.json uses the Vision schema", all(schema))
    lib.check(f"portable finds the faces Vision finds (median box iou >= {FACE_IOU})",
              faces and float(np.median(faces)) >= FACE_IOU and min(faces) > 0,
              f"n={len(faces)} median={np.median(faces):.2f} min={min(faces):.2f}")
    lib.check(f"portable pupils land on Vision's (median <= {PUPIL_MEDIAN:.0%}, max <= {PUPIL_MAX:.0%} of diagonal)",
              pupils and float(np.median(pupils)) <= PUPIL_MEDIAN and max(pupils) <= PUPIL_MAX,
              f"median={np.median(pupils):.4f} max={max(pupils):.4f}")
    for name, ious in masks.items():
        lib.check(f"portable {name} mask matches Vision (median iou >= {MASK_IOU})",
                  ious and float(np.median(ious)) >= MASK_IOU,
                  json.dumps({"n": len(ious), "median": round(float(np.median(ious)), 2) if ious else None,
                              "min": round(min(ious), 2) if ious else None}))
