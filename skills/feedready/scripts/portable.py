from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np

from detect import U2NETP, YUNET, Scene
from imaging import guided_filter, resize, save_mask

FACE_INPUT = 640
FACE_SCORE = 0.75
VISION_BOX = (-0.04, 0.147, 0.049, -0.026)
FACE_NMS = 0.3
SALIENT_INPUT = 320
SALIENT_THRESHOLD = 0.5
MIN_SHARE = 0.005
MAX_PROMPTS = 6


def vision(scene: Scene, out: Path) -> None:
    info: dict = {"backend": "portable", "faces": faces(scene.img)}
    sal = saliency(scene.img)
    regions = components(sal > SALIENT_THRESHOLD)
    info["salient_boxes"] = [r["box"] for r in regions[:1]]
    person = person_mask(scene)
    if person is not None:
        save_mask(person, out / "person.png")
        info["person"] = True
    subject = subject_mask(scene, sal, regions)
    if subject is not None:
        save_mask(subject, out / "subject.png")
        info["subject_instances"] = len(regions[:MAX_PROMPTS])
    (out / "vision.json").write_text(json.dumps(info, indent=2))


def _session(path: Path):
    import onnxruntime as ort

    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def faces(img: np.ndarray) -> list[dict]:
    H, W = img.shape[:2]
    scale = FACE_INPUT / max(H, W)
    w, h = max(1, round(W * scale)), max(1, round(H * scale))
    canvas = np.zeros((FACE_INPUT, FACE_INPUT, 3), np.float32)
    canvas[:h, :w] = resize(img, w, h)[..., ::-1] * 255
    session = _session(YUNET)
    outs = dict(zip([o.name for o in session.get_outputs()],
                    session.run(None, {"input": canvas.transpose(2, 0, 1)[None]})))
    boxes, scores, kps = [], [], []
    for stride in (8, 16, 32):
        n = FACE_INPUT // stride
        cols, rows = np.meshgrid(np.arange(n), np.arange(n))
        cols, rows = cols.ravel(), rows.ravel()
        score = np.sqrt(np.clip(outs[f"cls_{stride}"][0, :, 0], 0, 1) * np.clip(outs[f"obj_{stride}"][0, :, 0], 0, 1))
        keep = score >= FACE_SCORE
        if not keep.any():
            continue
        b = outs[f"bbox_{stride}"][0][keep]
        c, r = cols[keep], rows[keep]
        cx, cy = (c + b[:, 0]) * stride, (r + b[:, 1]) * stride
        bw, bh = np.exp(b[:, 2]) * stride, np.exp(b[:, 3]) * stride
        boxes.append(np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1))
        k = outs[f"kps_{stride}"][0][keep].reshape(-1, 5, 2)
        kps.append(np.stack([(k[..., 0] + c[:, None]) * stride, (k[..., 1] + r[:, None]) * stride], -1))
        scores.append(score[keep])
    if not boxes:
        return []
    boxes, scores, kps = np.concatenate(boxes), np.concatenate(scores), np.concatenate(kps)
    found = []
    for i in _nms(boxes, scores, FACE_NMS):
        x0, y0, x1, y1 = boxes[i]
        bw, bh = x1 - x0, y1 - y0
        dx0, dy0, dx1, dy1 = VISION_BOX
        box = np.array([x0 + dx0 * bw, y0 + dy0 * bh, x1 + dx1 * bw, y1 + dy1 * bh]) / scale / [W, H, W, H]
        pts = kps[i] / scale / [W, H]
        found.append({
            "box": [round(float(np.clip(v, 0, 1)), 5) for v in box],
            "confidence": round(float(scores[i]), 4),
            "left_pupil": [round(float(v), 5) for v in pts[0]],
            "right_pupil": [round(float(v), 5) for v in pts[1]],
        })
    return found


def _nms(boxes: np.ndarray, scores: np.ndarray, thresh: float) -> list[int]:
    order = list(np.argsort(-scores))
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep = []
    while order:
        i = order.pop(0)
        keep.append(int(i))
        rest = np.array(order, int)
        if not len(rest):
            break
        x0 = np.maximum(boxes[i, 0], boxes[rest, 0])
        y0 = np.maximum(boxes[i, 1], boxes[rest, 1])
        x1 = np.minimum(boxes[i, 2], boxes[rest, 2])
        y1 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
        iou = inter / (area[i] + area[rest] - inter + 1e-9)
        order = [j for j, v in zip(order, iou) if v <= thresh]
    return keep


def saliency(img: np.ndarray) -> np.ndarray:
    x = resize(img, SALIENT_INPUT, SALIENT_INPUT)
    x = x / max(float(x.max()), 1e-6)
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    session = _session(U2NETP)
    d = session.run(None, {session.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    lo, hi = float(d.min()), float(d.max())
    return ((d - lo) / max(hi - lo, 1e-6)).astype(np.float32)


def components(mask: np.ndarray, min_share: float = MIN_SHARE) -> list[dict]:
    H, W = mask.shape
    seen = np.zeros_like(mask, bool)
    found = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        seen[y0, x0] = True
        queue, ys, xs = deque([(y0, x0)]), [], []
        while queue:
            y, x = queue.popleft()
            ys.append(y)
            xs.append(x)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        share = len(ys) / (H * W)
        if share >= min_share:
            found.append({"share": share, "box": [min(xs) / W, min(ys) / H, (max(xs) + 1) / W, (max(ys) + 1) / H]})
    return sorted(found, key=lambda r: -r["share"])


def _pad(box: list[float], frac: float = 0.02) -> list[float]:
    x0, y0, x1, y1 = box
    return [max(0.0, x0 - frac), max(0.0, y0 - frac), min(1.0, x1 + frac), min(1.0, y1 + frac)]


def _prompted(scene: Scene, regions: list[dict], prior: np.ndarray) -> np.ndarray:
    H, W = scene.img.shape[:2]
    notes = list(scene.notes)
    out = guided_filter(scene.img, resize(prior, W, H), max(3, int(max(H, W) * 0.006)), 1e-4).clip(0, 1)
    for r in regions[:MAX_PROMPTS]:
        out = np.maximum(out, scene.object_mask(box=_pad(r["box"]))[0])
    scene.notes[:] = notes
    return out.astype(np.float32)


def person_mask(scene: Scene) -> np.ndarray | None:
    probs, labels = scene.segmentation()
    idx = [i for i, label in enumerate(labels) if label.split(",")[0].strip() == "person"]
    if not idx:
        return None
    prior = probs[idx].sum(0).clip(0, 1)
    regions = components(prior > 0.5)
    if not regions:
        return None
    return _prompted(scene, regions, prior)


def subject_mask(scene: Scene, sal: np.ndarray, regions: list[dict]) -> np.ndarray | None:
    if not regions:
        return None
    return _prompted(scene, regions, sal)
