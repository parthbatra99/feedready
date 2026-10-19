from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import bootstrap
import critique
import develop
import diagnose
import recrops
import masks as maskmod
import render
import review
from detect import (
    CACHE,
    MissingCapability,
    Scene,
    bootstrap_hint,
    edgetam_available,
    engine_available,
    engine_stale,
    run_engine,
    segformer_available,
    vision_backend,
)
from imaging import cv2, icc_profile, is_p3, load_rgb, luma, save_jpeg, save_png16

USAGE = """feedready: render Claude's photo-edit recipes, version by version, and export a post-ready image.

  feedready.py doctor                            tier, capabilities, and what's missing
  feedready.py probe                             what this sandbox has: python, packages, network, disk
  feedready.py bootstrap FEATURE... [--from DIR] install packages + models for people, segment, object, heal,
                                                 heic, opencv or all (--from: verify files already uploaded)
  feedready.py inspect IMG [--fetch]             grid overlay + stats + profile + findings (JSON); --fetch first
                                                 downloads the models this photo needs (scene; people if present)
  feedready.py masks RECIPE IMG                  contact sheet of every step's mask
  feedready.py board IMG RECIPE [RECIPE ...]     original + each recipe side by side (directions, versions)
  feedready.py preview RECIPE IMG [--note TEXT]  screen-size render saved as the next version, with critique
  feedready.py apply RECIPE IMG [-o OUT]         full-resolution export + before/after compare

RECIPE is a path to a JSON file, an inline JSON string (reference/recipe.md), or a
saved version such as v3. On a Mac, Core Image + Vision render and detect (feedready-engine);
elsewhere numpy renders and the portable models (bootstrap) detect people, faces, scenes and objects.
"""

CLAUDE_OUTPUTS = Path("/mnt/user-data/outputs")
LARGE_MEGAPIXELS = 30
WORKING_COPY_VERSION = 2
PREVIEW_EDGE = 1600
SINGLE_EDGE = 900
BOARD_EDGE = 900
SIMILAR = 0.025
FETCH_CAP_MB = 100
PERSON_SHARE = 0.002
INSPECT_GAINS = {
    "people": "face, subject-balance and crop checks that know where people are; person, subject, background and face masks",
    "segment": "haze and sky checks and the scene read behind the genre; sky and scenery masks that follow the horizon",
    "opencv": "the distraction check and sharper mask edges",
}
VERSION = re.compile(r"[vV]\d+")


def tier() -> str:
    if engine_available():
        return "mac"
    return "portable" if vision_backend() == "portable" else "basic"


def output_dir() -> Path:
    if CLAUDE_OUTPUTS.exists():
        return CLAUDE_OUTPUTS
    return Path.home() / "Pictures" / "feedready"


def prepare(src: Path) -> tuple[Path, Path, np.ndarray]:
    h = hashlib.sha1()
    with open(src, "rb") as f:
        h.update(f.read(1 << 20))
    h.update(str(src.stat().st_size).encode())
    h.update(str(WORKING_COPY_VERSION).encode())
    work = Path(os.environ.get("FEEDREADY_WORK", CACHE / "work")) / f"{src.stem}-{h.hexdigest()[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    working = work / "working.png"
    if not working.exists():
        if engine_available():
            run_engine("decode", str(src), str(working))
        else:
            icc = icc_profile(src)
            save_png16(load_rgb(src), working, icc if is_p3(icc) else None)
    return work, working, load_rgb(working)


def wide_profile(working: Path) -> bytes | None:
    icc = icc_profile(working)
    return icc if is_p3(icc) else None


def versions_dir(work: Path) -> Path:
    return work / "versions"


def version_numbers(work: Path) -> list[int]:
    return sorted(int(p.stem[1:]) for p in versions_dir(work).glob("v*.json") if re.fullmatch(r"v\d+", p.stem))


def version_index(work: Path) -> dict:
    path = versions_dir(work) / "index.json"
    return json.loads(path.read_text()) if path.exists() else {}


def taste(work_root: Path | None = None) -> dict:
    root = work_root or CACHE / "work"
    looks: dict[str, list[float]] = {}
    sliders: dict[str, list[float]] = {}
    presets: dict[str, int] = {}
    vignettes = 0
    photos = 0
    notes: list[str] = []
    for work in sorted(root.glob("*")):
        if not work.is_dir():
            continue
        numbers = version_numbers(work)
        if not numbers:
            continue
        photos += 1
        for n in numbers:
            recipe = json.loads((versions_dir(work) / f"v{n}.json").read_text())
            weight = 2 if n == numbers[-1] else 1
            for step in recipe.get("steps", []):
                if look := step.get("look"):
                    looks.setdefault(look, []).extend([step.get("amount", 100)] * weight)
                for key, val in (step.get("adjust") or {}).items():
                    if isinstance(val, (int, float)):
                        sliders.setdefault(key, []).extend([abs(val)] * weight)
            if "vignette" in recipe:
                vignettes += weight
            if preset := recipe.get("preset"):
                presets[preset] = presets.get(preset, 0) + weight
        notes += [str(m.get("note", "")).strip() for m in version_index(work).values()
                  if str(m.get("note", "")).strip()]
    if not photos:
        return {}

    def median(vals):
        s = sorted(vals)
        return round(s[len(s) // 2], 1)

    return {
        "photos_edited": photos,
        "look_use": {k: {"times": len(v), "median_amount": median(v)}
                     for k, v in sorted(looks.items(), key=lambda kv: -len(kv[1]))[:6]},
        "slider_medians": {k: median(v) for k, v in sorted(sliders.items(), key=lambda kv: -len(kv[1]))[:8]},
        "vignette_use": vignettes,
        "presets": dict(sorted(presets.items(), key=lambda kv: -kv[1])),
        "recent_notes": notes[-8:],
    }


def load_recipe(arg: str, work: Path) -> dict:
    if VERSION.fullmatch(arg.strip()):
        path = versions_dir(work) / f"v{int(arg.strip()[1:])}.json"
        if not path.exists():
            have = ", ".join(f"v{n}" for n in version_numbers(work)) or "none yet"
            raise render.fail(f"no version {arg} for this photo (saved: {have})")
        recipe = json.loads(path.read_text())
    else:
        text = arg if arg.lstrip().startswith("{") else Path(arg).expanduser().read_text()
        try:
            recipe = json.loads(text)
        except json.JSONDecodeError as e:
            raise render.fail(f"recipe is not valid JSON: {e}")
    recipe.setdefault("steps", [])
    return recipe


def stats(img: np.ndarray) -> dict:
    lum = luma(img)
    return {
        "mean_luma": round(float(lum.mean()), 3),
        "p01_p99_luma": [round(float(np.percentile(lum, 1)), 3), round(float(np.percentile(lum, 99)), 3)],
        "clipped_highlights_pct": round(float((img.max(-1) >= 0.995).mean() * 100), 2),
        "crushed_shadows_pct": round(float((lum <= 0.01).mean() * 100), 2),
    }


def capabilities() -> dict:
    return {
        "people": vision_backend() or False,
        "segment": segformer_available(),
        "object": edgetam_available(),
        "heal": develop.heal_backend() or False,
        "heic": engine_available() or bootstrap.has_module("pillow_heif"),
        "opencv": bootstrap.has_module("cv2.ximgproc"),
    }


def _missing(caps: dict) -> list[str]:
    out = []
    mac = sys.platform == "darwin" and not os.environ.get("FEEDREADY_NO_ENGINE")
    if mac and not engine_available():
        out.append("engine: run setup.sh (compiles Swift, no download)")
    elif engine_stale():
        out.append("engine: built from an older version of this skill; rerun setup.sh (no download)")
    for feature, have in caps.items():
        if have or (mac and feature in ("people", "heic")):
            continue
        out.append(f"{feature}: {bootstrap_hint(feature)}: {bootstrap.manifest()['features'][feature]['gives']}")
    return out


def cmd_doctor(_args) -> dict:
    caps = capabilities()
    return {
        "tier": tier(),
        "python": sys.version.split()[0],
        "renderer": "core-image" if engine_available() else "numpy",
        "capabilities": caps,
        "output_dir": str(output_dir()),
        "missing": _missing(caps),
    }


def cmd_probe(_args) -> dict:
    return bootstrap.probe()


def cmd_bootstrap(args) -> dict:
    source = Path(args.source).expanduser() if args.source else None
    if source is not None and not source.is_dir():
        return {"error": f"{source} is not a folder"}
    out = bootstrap.bootstrap(args.features, source)
    if "error" not in out:
        out["capabilities"] = capabilities()
    return out


def _fetch(feature: str, why: str) -> dict | None:
    need = bootstrap.missing(feature)
    if not need["models"] and not need["packages"]:
        return None
    entry = {"feature": feature, "mb": need["mb"], "why": why}
    if need["mb"] > FETCH_CAP_MB:
        return {**entry, "ok": False, "error": f"over the {FETCH_CAP_MB} MB auto-download limit; ask first"}
    result = bootstrap.bootstrap([feature])
    entry["ok"] = result["ready"][feature]
    if notes := bootstrap.notices(need["models"]):
        entry["licence"] = notes
    if not entry["ok"]:
        entry["error"] = result["models"].get("error") or result["packages"].get("error")
        if result.get("fallback"):
            entry["fallback"] = result["fallback"]
    return entry


def _person_in_frame(scene: Scene) -> bool:
    probs, labels = scene.segmentation()
    idx = [i for i, label in enumerate(labels) if label.split(",")[0].strip() == "person"]
    return bool(idx) and float((probs.argmax(0) == idx[0]).mean()) >= PERSON_SHARE


def fetch_for(scene: Scene) -> list[dict]:
    fetched = []
    if done := _fetch("segment", "sky and scenery masks that follow the horizon, and the scene read behind the genre"):
        fetched.append(done)
    if not engine_available() and segformer_available() and _person_in_frame(scene):
        if done := _fetch("people", "there's a person in the frame: person, subject and face masks"):
            fetched.append(done)
    importlib.invalidate_caches()
    return fetched


def cmd_inspect(args) -> dict:
    src = Path(args.image).expanduser()
    work, working, img = prepare(src)
    scene = Scene(work, working, img)
    fetched = fetch_for(scene) if getattr(args, "fetch", False) else []
    out = {"work_dir": str(work), "size": [img.shape[1], img.shape[0]], "tier": tier(), "stats": stats(img)}
    if fetched:
        out["fetched"] = fetched
    out.update(_resolution(img, src))
    icc = wide_profile(working)
    out["color_space"] = "display-p3" if icc else "srgb"
    faces = []
    if backend := vision_backend():
        out["vision"] = backend
        v = scene.vision()
        faces = v.get("faces", [])
        out["faces"] = [{k: f.get(k) for k in ("box", "left_pupil", "right_pupil", "confidence")} for f in faces]
        out["person_mask"] = bool(v.get("person"))
        out["subject_instances"] = v.get("subject_instances", 0)
        out["salient_boxes"] = v.get("salient_boxes", [])
        if "horizon_degrees" in v:
            out["horizon_degrees"] = round(v["horizon_degrees"], 2)
    if segformer_available():
        out["scene_classes"] = scene.segment_summary()
    out["profile"] = diagnose.profile(scene)
    out["diagnostics"] = diagnose.run(scene)
    opp = diagnose.run_opportunities(scene)
    out["opportunities"] = opp["opportunities"]
    if opp["skipped"]:
        out["diagnostics"]["skipped"] += opp["skipped"]
    out["recrops"] = recrops.mine(scene)
    caps = capabilities()
    if not getattr(args, "fetch", False) and (unlock := [{"feature": f, "command": bootstrap_hint(f), "adds": gain}
                                                         for f, gain in INSPECT_GAINS.items() if not caps[f]]):
        out["unlock"] = unlock
    if numbers := version_numbers(work):
        index = version_index(work)
        out["previous_versions"] = [{"version": f"v{n}", "note": index.get(str(n), {}).get("note", "")} for n in numbers]
    if history := taste():
        out["taste"] = history
    grid = work / "grid.jpg"
    review.grid_image(img, faces, grid, icc)
    out["grid"] = str(grid)
    out["original"] = str(working)
    return out


def _resolution(img: np.ndarray, src: Path) -> dict:
    mp = img.shape[0] * img.shape[1] / 1e6
    return {
        "megapixels": round(mp, 1),
        "file_mb": round(src.stat().st_size / 1e6, 1),
        "large": mp > LARGE_MEGAPIXELS,
    }


def _step_masks(steps: list[dict], scene: Scene) -> list[np.ndarray | None]:
    result = []
    for i, step in enumerate(steps):
        try:
            result.append(maskmod.build(step.get("mask"), scene))
        except (MissingCapability, ValueError) as e:
            raise SystemExit(json.dumps({"error": f"step {i + 1} ({step.get('name', '')}): {e}", "tier": tier()}))
    return result


def cmd_masks(args) -> dict:
    src = Path(args.image).expanduser()
    work, working, img = prepare(src)
    recipe = load_recipe(args.recipe, work)
    scene = Scene(work, working, img)
    built = _step_masks(recipe["steps"], scene)
    if not built:
        return {"error": "recipe has no steps"}
    path = work / "masks.jpg"
    review.mask_sheet(img, recipe["steps"], built, path, wide_profile(working))
    coverage = [None if m is None else round(float(m.mean()), 3) for m in built]
    return {"contact_sheet": str(path), "mask_coverage": coverage, "notes": scene.notes}


class Session:
    def __init__(self, src: Path):
        self.src = src
        self.work, self.working, self.img = prepare(src)
        self.scene = Scene(self.work, self.working, self.img)
        self.icc = wide_profile(self.working)
        self.engine = engine_available()
        self.stage = self.work / "stage"
        self.stage.mkdir(exist_ok=True)

    def recipe(self, arg: str) -> dict:
        return load_recipe(arg, self.work)

    def prepare_steps(self, recipe: dict):
        steps, warnings = render.resolve(recipe)
        return steps, _step_masks(steps, self.scene), warnings

    def scaled(self, built: list, edge: int):
        small, small_masks = render.downscale(self.img, built, edge)
        if not self.engine:
            return small, small_masks, None
        path = self.stage / f"base-{small.shape[1]}x{small.shape[0]}.png"
        if not path.exists():
            save_png16(small, path, self.icc)
        return small, small_masks, path

    def render(self, img, steps, built, recipe, out, tag, source, **kw):
        return render.render(img, steps, built, recipe, out, stage=self.stage, tag=tag, engine=self.engine,
                             icc=self.icc, source=source, **kw)


def cmd_apply(args) -> dict:
    s = Session(Path(args.image).expanduser())
    recipe = s.recipe(args.recipe)
    steps, built, warnings = s.prepare_steps(recipe)
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ref = args.recipe.strip()
    suffix = ref.lower() if VERSION.fullmatch(ref) else recipe.get("preset", "edit")
    out = Path(args.output).expanduser() if args.output else out_dir / f"{s.src.stem}-{suffix}.jpg"
    crop = render.render(s.img, steps, built, recipe, out, stage=s.work, tag="apply", engine=s.engine, icc=s.icc,
                         source=s.working)
    result = load_rgb(out)
    before = render.frame(s.img, crop)
    compare = out.with_name(out.stem + "-compare.jpg")
    review.pair(before, result, ("before", "after"), compare, s.icc)
    (s.work / "last_recipe.json").write_text(json.dumps(recipe, indent=2))
    return {
        "output": str(out),
        "compare": str(compare),
        "size": [result.shape[1], result.shape[0]],
        "file_mb": round(out.stat().st_size / 1e6, 1),
        "color_space": "display-p3" if s.icc else "srgb",
        "renderer": "core-image" if s.engine else "numpy",
        "before": stats(before),
        "after": stats(result),
        "warnings": warnings,
        "notes": s.scene.notes,
    }


def _frame_faces(scene: Scene, crop, W: int, H: int) -> list[list[float]]:
    try:
        faces = scene.faces()
    except MissingCapability:
        return []
    x, y, w, h = crop if crop else (0, 0, W, H)
    out = []
    for f in faces:
        x0, y0, x1, y1 = f["box"]
        box = [(x0 * W - x) / w, (y0 * H - y) / h, (x1 * W - x) / w, (y1 * H - y) / h]
        if box[2] > 0 and box[3] > 0 and box[0] < 1 and box[1] < 1:
            out.append([min(max(v, 0.0), 1.0) for v in box])
    return out


def _frame_person(scene: Scene, small: np.ndarray, crop) -> np.ndarray | None:
    person = diagnose.person_mask(scene)
    if person is None:
        return None
    H, W = small.shape[:2]
    _, (scaled,) = render.downscale(scene.img, [person], max(H, W))
    return render.frame(scaled, crop)


def _singles(s: Session, recipe: dict, steps: list[dict], built: list):
    tiny, tiny_masks, source = s.scaled(built, SINGLE_EDGE)
    singles, impacts = [], []
    for i, (step, m) in enumerate(zip(steps, tiny_masks)):
        out = s.stage / f"single-{i}.png"
        s.render(tiny, [step], [m], {"steps": [step]}, out, f"single{i}", source, framed=False)
        alone = load_rgb(out)
        imp = critique.impact(tiny, alone, m)
        impacts.append(imp)
        raw = recipe["steps"][i]
        singles.append({"index": i, "name": step.get("name", f"step {i + 1}"), "why": step.get("why", ""),
                        "summary": review.describe(raw.get("adjust", {}), raw.get("look"), raw.get("amount")),
                        "after": alone, "mask": m, **imp})
    return tiny, singles, impacts


def cmd_preview(args) -> dict:
    s = Session(Path(args.image).expanduser())
    recipe = s.recipe(args.recipe)
    steps, built, warnings = s.prepare_steps(recipe)
    vdir = versions_dir(s.work)
    vdir.mkdir(exist_ok=True)
    previous = version_numbers(s.work)
    n = (previous[-1] if previous else 0) + 1
    tag = f"v{n}"

    small, small_masks, source = s.scaled(built, PREVIEW_EDGE)
    out = vdir / f"{tag}.jpg"
    crop = s.render(small, steps, small_masks, recipe, out, "preview", source, full_size=False)
    after = load_rgb(out)
    before = render.frame(small, crop)
    before_path = vdir / ("before-" + "-".join(map(str, crop or (0, 0, small.shape[1], small.shape[0]))) + ".jpg")
    if not before_path.exists():
        save_jpeg(before, before_path, 92, s.icc)

    tiny, singles, impacts = _singles(s, recipe, steps, built)
    faces = _frame_faces(s.scene, crop, small.shape[1], small.shape[0]) if vision_backend() else []
    person = _frame_person(s.scene, small, crop) if vision_backend() else None
    verdict = critique.run(before, after, faces, person, recipe.get("vignette", 0), steps, impacts)

    compare = vdir / f"{tag}-compare.jpg"
    review.pair(before, after, ("before", tag), compare, s.icc)
    diff = None
    if previous:
        last = f"v{previous[-1]}"
        diff = vdir / f"{last}-{tag}.jpg"
        review.pair(load_rgb(vdir / f"{last}.jpg"), after, (last, tag), diff, s.icc)
    edit_map = vdir / f"{tag}-map.jpg"
    review.edit_map(small, steps, small_masks, edit_map, s.icc)
    cards = None
    if singles:
        cards = vdir / f"{tag}-cards.jpg"
        review.cards(tiny, singles, cards, s.icc)

    (vdir / f"{tag}.json").write_text(json.dumps(recipe, indent=2))
    index = version_index(s.work)
    index[str(n)] = {"note": args.note, "before": before_path.name, "verdict": verdict["verdict"]}
    (vdir / "index.json").write_text(json.dumps(index, indent=2))
    page = s.work / "review.html"
    review.review_html(f"{s.src.stem} · {tag}", [
        {"n": k, "note": index.get(str(k), {}).get("note", ""), "after": vdir / f"v{k}.jpg",
         "before": vdir / index.get(str(k), {}).get("before", before_path.name)}
        for k in version_numbers(s.work)], page)

    return {
        "version": tag,
        "preview": str(out),
        "compare": str(compare),
        "diff": str(diff) if diff else None,
        "map": str(edit_map),
        "cards": str(cards) if cards else None,
        "review": str(page),
        "critique": verdict,
        "impact": [{"step": i + 1, "name": st.get("name", ""), "level": imp["level"], "delta": imp["delta"],
                    "reach": imp["reach"]} for i, (st, imp) in enumerate(zip(steps, impacts))],
        "after": stats(after),
        "warnings": warnings,
        "notes": s.scene.notes,
    }


def cmd_board(args) -> dict:
    s = Session(Path(args.image).expanduser())
    tiles = [("original", "as shot", render.downscale(s.img, [], BOARD_EDGE)[0])]
    index = version_index(s.work)
    for i, arg in enumerate(args.recipes):
        recipe = s.recipe(arg)
        steps, built, _ = s.prepare_steps(recipe)
        small, small_masks, source = s.scaled(built, BOARD_EDGE)
        out = s.stage / f"board-{i}.png"
        s.render(small, steps, small_masks, recipe, out, f"board{i}", source, full_size=False)
        ref = arg.strip()
        is_version = VERSION.fullmatch(ref) is not None
        if is_version:
            title, note = f"v{int(ref[1:])}", index.get(str(int(ref[1:])), {}).get("note", "")
        else:
            title, note = recipe.get("label") or chr(ord("A") + i), recipe.get("note", "")
        if not note:
            note = ", ".join(f"{st['look']} look" if st.get("look") else st.get("name", "") for st in recipe["steps"])
        tiles.append((title, note, load_rgb(out)))
    path = s.work / "board.jpg"
    review.board(tiles, path, s.icc)
    pairs = critique.distinctness([t[2] for t in tiles])
    names = [t[0] for t in tiles]
    alike = [f"{names[i]} and {names[j]} look alike (difference {d})" for (i, j), d in
             ((pr["pair"], pr["delta"]) for pr in pairs) if d < SIMILAR]
    return {"board": str(path), "tiles": names, "too_similar": alike,
            "differences": {f"{names[pr['pair'][0]]} | {names[pr['pair'][1]]}": pr["delta"] for pr in pairs}}


def main():
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("probe")
    p = sub.add_parser("bootstrap")
    p.add_argument("features", nargs="+")
    p.add_argument("--from", dest="source")
    p = sub.add_parser("inspect")
    p.add_argument("image")
    p.add_argument("--fetch", action="store_true")
    p = sub.add_parser("masks")
    p.add_argument("recipe")
    p.add_argument("image")
    p = sub.add_parser("board")
    p.add_argument("image")
    p.add_argument("recipes", nargs="+")
    p = sub.add_parser("preview")
    p.add_argument("recipe")
    p.add_argument("image")
    p.add_argument("--note", default="")
    p = sub.add_parser("apply")
    p.add_argument("recipe")
    p.add_argument("image")
    p.add_argument("-o", "--output")
    args = ap.parse_args()
    handler = {"doctor": cmd_doctor, "probe": cmd_probe, "bootstrap": cmd_bootstrap, "inspect": cmd_inspect,
               "masks": cmd_masks, "board": cmd_board, "preview": cmd_preview, "apply": cmd_apply}[args.cmd]
    try:
        result = handler(args)
    except MissingCapability as e:
        raise SystemExit(json.dumps({"error": str(e), "tier": tier()}))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
