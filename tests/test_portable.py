from __future__ import annotations

import json

import numpy as np

import lib
import critique
import detect
import masks as maskmod
from imaging import linear_to_srgb, load_mask, resize, srgb_to_linear

FACE_IOU = 0.7
PUPIL_MEDIAN = 0.01
PUPIL_MAX = 0.03
MASK_IOU = 0.8
MIN_SHARE = 0.05
HALO_MEDIAN = 0.10
PERSON_MIN_IOU = 0.5
BACKGROUND_EV = -0.4


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


def _darken_background(img, m):
    return linear_to_srgb(srgb_to_linear(img) * (1 + (2 ** BACKGROUND_EV - 1) * (1 - m))[..., None]).clip(0, 1)


def _halo(img, used, edge):
    h = critique._halo(img, _darken_background(img, used), edge)
    return None if h is None else abs(h)


def _compare(src, faces, pupils, masks, halos):
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
        if name == "person" and (apple["faces"] or portable["faces"]):
            masks["person_with_face"].append(masks[name][-1])
        if b is None:
            continue
        soft_a = resize(load_mask(work / "vision" / f"{name}.png"), W, H)
        soft_b = resize(load_mask(portable_dir / f"{name}.png"), W, H)
        for key, used, edge in (("vision", soft_a, soft_a), ("own", soft_b, soft_b), ("true", soft_b, soft_a)):
            if (h := _halo(img, used, edge)) is not None:
                halos[name][key].append(h)
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
    faces, pupils, masks, schema = [], [], {"person": [], "subject": [], "person_with_face": []}, []
    halos = {n: {"vision": [], "own": [], "true": []} for n in ("person", "subject")}
    for src in photos:
        schema.append(_compare(src, faces, pupils, masks, halos))
    lib.check("portable vision.json uses the Vision schema", all(schema))
    lib.check(f"portable finds the faces Vision finds (median box iou >= {FACE_IOU})",
              faces and float(np.median(faces)) >= FACE_IOU and min(faces) > 0,
              f"n={len(faces)} median={np.median(faces):.2f} min={min(faces):.2f}")
    lib.check(f"portable pupils land on Vision's (median <= {PUPIL_MEDIAN:.0%}, max <= {PUPIL_MAX:.0%} of diagonal)",
              pupils and float(np.median(pupils)) <= PUPIL_MEDIAN and max(pupils) <= PUPIL_MAX,
              f"median={np.median(pupils):.4f} max={max(pupils):.4f}")
    for name in ("person", "subject"):
        ious = masks[name]
        lib.check(f"portable {name} mask matches Vision (median iou >= {MASK_IOU})",
                  ious and float(np.median(ious)) >= MASK_IOU,
                  json.dumps({"n": len(ious), "median": round(float(np.median(ious)), 2) if ious else None,
                              "min": round(min(ious), 2) if ious else None}))
    seen = masks["person_with_face"]
    lib.check(f"portable person mask never misses someone with a face (iou >= {PERSON_MIN_IOU} on every such photo)",
              seen and min(seen) >= PERSON_MIN_IOU, f"n={len(seen)} min={min(seen):.2f}" if seen else "no person photos")
    for name, h in halos.items():
        med = {k: round(float(np.median(v)), 3) if v else None for k, v in h.items()}
        lib.check(f"portable {name} edges don't halo a {BACKGROUND_EV} EV background move "
                  f"(median <= {HALO_MEDIAN} stops, own edge and Vision's edge)",
                  h["own"] and med["own"] <= HALO_MEDIAN and med["true"] <= HALO_MEDIAN, json.dumps(med))
    people_and_skin()


def people_and_skin():
    import feedready

    group = lib.CORPUS / "commons" / "group.jpg"
    portrait = lib.CORPUS / "commons" / "portrait-light.jpg"
    if not (group.exists() and portrait.exists()):
        lib.skip("person faces and skin masks", "no corpus: selftest.py --fetch-corpus")
        return
    with lib.isolated_work(), lib.portable_tier():
        work, working, img = feedready.prepare(group)
        scene = detect.Scene(work, working, img)
        faces = scene.faces()
        main = detect.main_faces(faces)
        everyone = scene.vision_mask("person")
        picked = maskmod.build({"type": "person", "faces": main[:2]}, scene)
        H, W = img.shape[:2]
        centre = lambda k: (int((faces[k]["box"][1] + faces[k]["box"][3]) / 2 * H),
                            int((faces[k]["box"][0] + faces[k]["box"][2]) / 2 * W))
        lib.check("person with faces keeps the chosen people",
                  all(picked[centre(k)] > 0.5 for k in main[:2]), str([float(picked[centre(k)]) for k in main[:2]]))
        lib.check("person with faces leaves the other people out",
                  all(picked[centre(k)] < 0.5 for k in main[2:]) and picked.mean() < 0.7 * everyone.mean(),
                  f"{[round(float(picked[centre(k)]), 2) for k in main[2:]]} {picked.mean():.3f}/{everyone.mean():.3f}")

        work, working, img = feedready.prepare(portrait)
        scene = detect.Scene(work, working, img)
        f = scene.faces()[0]["box"]
        H, W = img.shape[:2]
        box = (slice(int(f[1] * H), int(f[3] * H)), slice(int(f[0] * W), int(f[2] * W)))
        skin = maskmod.build({"type": "skin"}, scene)
        person = scene.vision_mask("person")
        hue = maskmod.build({"op": "intersect", "masks": [
            {"type": "person"}, {"type": "color", "hue": 22, "range": 12, "soft": 8, "min_sat": 0.12}]}, scene)
        tv = lambda m: float(np.abs(np.diff(m[box], axis=0)).mean() + np.abs(np.diff(m[box], axis=1)).mean())
    lib.check("skin mask covers the face", float(skin[box].mean()) >= 0.5, f"{skin[box].mean():.2f}")
    lib.check("skin mask stays off the background", float(skin[person < 0.1].mean()) <= 0.01,
              f"{skin[person < 0.1].mean():.4f}")
    lib.check("skin mask is smoother than a colour-range skin mask (the patchy look)", tv(skin) < 0.5 * tv(hue),
              f"skin {tv(skin):.4f} vs colour range {tv(hue):.4f}")
