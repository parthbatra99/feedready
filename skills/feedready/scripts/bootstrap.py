from __future__ import annotations

import functools
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from detect import MODELS

MANIFEST = Path(__file__).resolve().parents[1] / "models.json"
UPLOADS = Path("/mnt/user-data/uploads")
PROBE_URLS = {
    "pypi": "https://pypi.org/simple/onnxruntime/",
    "pythonhosted": "https://files.pythonhosted.org/packages/source/s/six/six-1.16.0.tar.gz",
    "huggingface": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    "github": "https://github.com/",
    "github_release": "https://github.com/cli/cli/releases/download/v2.40.0/gh_2.40.0_checksums.txt",
}


@functools.cache
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def has_module(name: str) -> bool:
    head, *rest = name.split(".")
    if importlib.util.find_spec(head) is None:
        return False
    if not rest:
        return True
    try:
        mod = importlib.import_module(head)
    except ImportError:
        return False
    for attr in rest:
        if not hasattr(mod, attr):
            return False
        mod = getattr(mod, attr)
    return True


def model_ready(name: str) -> bool:
    return all((MODELS / f["path"]).exists() for f in manifest()["models"][name]["files"])


def model_bytes(names) -> int:
    m = manifest()["models"]
    return sum(f["bytes"] for n in names for f in m[n]["files"])


def missing(feature: str) -> dict:
    spec = manifest()["features"][feature]
    packages = manifest()["packages"]
    models = [n for n in spec["models"] if not model_ready(n)]
    return {
        "models": models,
        "packages": [p for p in spec["packages"] if not has_module(packages[p]["module"])],
        "mb": round(model_bytes(models) / 1e6, 1),
    }


def notices(names) -> list[str]:
    m = manifest()["models"]
    return [f"{m[n]['what']}: {m[n]['notice']}" for n in names if m[n].get("notice")]


def megabytes(names) -> str:
    return f"{model_bytes(names) / 1e6:.1f} MB"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    errors = []
    if shutil.which("curl"):
        res = subprocess.run(["curl", "-sSfL", "--retry", "2", "-o", str(dest), url], capture_output=True, text=True)
        if res.returncode == 0:
            return
        errors.append(res.stderr.strip() or f"curl exit {res.returncode}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"could not download {url}: {'; '.join([*errors, str(e)])}") from None


def asset_name(entry: dict) -> str:
    return entry["path"].replace("/", "-")


def sources(entry: dict) -> list[str]:
    return [entry["url"], *(base.rstrip("/") + "/" + asset_name(entry) for base in manifest().get("mirrors", []))]


def _install_file(entry: dict, source: Path | None) -> str:
    dest = MODELS / entry["path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if source is not None:
        shutil.copyfile(source, part)
        if _sha256(part) != entry["sha256"]:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"checksum mismatch for {entry['path']}")
    else:
        errors = []
        for url in sources(entry):
            try:
                _download(url, part)
            except RuntimeError as e:
                errors.append(str(e))
                continue
            if _sha256(part) == entry["sha256"]:
                break
            part.unlink(missing_ok=True)
            errors.append(f"checksum mismatch for {entry['path']} from {url}")
        else:
            raise RuntimeError("; ".join(errors))
    part.replace(dest)
    return entry["path"]


def _uploaded(folder: Path) -> dict[str, Path]:
    wanted: dict[int, set[str]] = {}
    for model in manifest()["models"].values():
        for e in model["files"]:
            wanted.setdefault(e["bytes"], set()).add(e["sha256"])
    found = {}
    for path in folder.rglob("*"):
        if path.is_file() and path.stat().st_size in wanted:
            digest = _sha256(path)
            if digest in wanted[path.stat().st_size]:
                found[digest] = path
    return found


def _needed(entry: dict) -> dict:
    return {"file": Path(entry["path"]).name, "urls": sources(entry), "bytes": entry["bytes"]}


def stage_assets(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    staged = []
    for model in manifest()["models"].values():
        for entry in model["files"]:
            src = MODELS / entry["path"]
            if not src.exists():
                raise RuntimeError(f"{entry['path']} isn't installed; run setup.sh --segformer --models first")
            if _sha256(src) != entry["sha256"]:
                raise RuntimeError(f"{entry['path']} doesn't match its pinned sha256")
            shutil.copyfile(src, out / asset_name(entry))
            staged.append(asset_name(entry))
    return staged


def fetch_models(names, source: Path | None = None) -> dict:
    uploads = _uploaded(source) if source is not None else {}
    got, need = [], []
    for name in names:
        for entry in manifest()["models"][name]["files"]:
            if (MODELS / entry["path"]).exists():
                continue
            if source is not None:
                if entry["sha256"] in uploads:
                    got.append(_install_file(entry, uploads[entry["sha256"]]))
                else:
                    need.append(_needed(entry))
                continue
            got.append(_install_file(entry, None))
    return {"installed": got, "still_needed": need}


def install_packages(names) -> dict:
    packages = manifest()["packages"]
    todo = [n for n in names if not has_module(packages[n]["module"])]
    if not todo:
        return {"installed": [], "error": None}
    specs = [packages[n]["spec"] for n in todo]
    if not _has_pip() and shutil.which("uv"):
        res = subprocess.run(["uv", "pip", "install", "-q", "--python", sys.executable, *specs],
                             capture_output=True, text=True)
    else:
        base = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
        if sys.prefix == sys.base_prefix:
            base.append("--user")
        res = subprocess.run([*base, "--break-system-packages", *specs], capture_output=True, text=True)
        if res.returncode != 0 and "no such option" in res.stderr:
            res = subprocess.run([*base, *specs], capture_output=True, text=True)
    if res.returncode != 0:
        return {"installed": [], "error": res.stderr.strip()[-600:]}
    importlib.invalidate_caches()
    return {"installed": todo, "error": None}


def bootstrap(features, source: Path | None = None) -> dict:
    spec = manifest()["features"]
    if "all" in features:
        features = list(spec)
    unknown = [f for f in features if f not in spec]
    if unknown:
        return {"error": f"unknown feature {', '.join(unknown)}; choose from {', '.join(spec)} or all"}
    models = list(dict.fromkeys(m for f in features for m in spec[f]["models"]))
    packages = list(dict.fromkeys(p for f in features for p in spec[f]["packages"]))
    out = {"features": features, "packages": install_packages(packages)}
    try:
        out["models"] = fetch_models(models, source)
    except Exception as e:
        needed = [_needed(f) for n in models for f in manifest()["models"][n]["files"]
                  if not (MODELS / f["path"]).exists()]
        out["models"] = {"error": str(e), "still_needed": needed}
        if source is None:
            out["fallback"] = ("downloads are blocked here: allow the domain in the sandbox's network settings, or "
                               f"attach the files in still_needed to the chat and rerun bootstrap with --from {UPLOADS}")
    out["ready"] = {f: not any(missing(f)[k] for k in ("models", "packages")) for f in features}
    return out


def _reachable(url: str) -> dict:
    if shutil.which("curl"):
        res = subprocess.run(["curl", "-sS", "-o", os.devnull, "-r", "0-0", "-L", "--max-time", "15",
                              "-w", "%{http_code} %{url_effective}", url], capture_output=True, text=True)
        code, _, final = res.stdout.partition(" ")
        if res.returncode == 0 and code.isdigit() and int(code) < 400:
            return {"ok": True, "via": urllib.parse.urlsplit(final).hostname}
        return {"ok": False, "error": res.stderr.strip() or f"http {code}"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "feedready-probe", "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"ok": r.status < 400, "via": urllib.parse.urlsplit(r.geturl()).hostname}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _has_pip() -> bool:
    return importlib.util.find_spec("pip") is not None


def probe() -> dict:
    pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True)
    home = Path.home()
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "executable": sys.executable,
        "in_venv": sys.prefix != sys.base_prefix,
        "pip": pip.stdout.split(" from ")[0] if pip.returncode == 0 else None,
        "curl": shutil.which("curl") is not None,
        "modules": {m: has_module(m) for m in
                    ("numpy", "PIL", "cv2", "cv2.ximgproc", "cv2.xphoto", "onnxruntime", "pillow_heif")},
        "network": {name: _reachable(url) for name, url in PROBE_URLS.items()},
        "proxy": any(os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY")),
        "home": str(home),
        "free_mb": round(shutil.disk_usage(home).free / 1e6),
        "uploads_dir": UPLOADS.exists(),
        "models": {n: model_ready(n) for n in manifest()["models"]},
        "mirrors": manifest().get("mirrors", []),
    }


if __name__ == "__main__":
    names = sys.argv[1:]
    if names[:1] == ["assets"] and len(names) == 2:
        try:
            staged = stage_assets(Path(names[1]).expanduser())
        except RuntimeError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        print("\n".join(staged))
        sys.exit(0)
    if names != ["probe"] and (not names or any(n not in manifest()["models"] for n in names)):
        print(f"usage: bootstrap.py probe | assets OUTDIR | MODEL... ({', '.join(manifest()['models'])})",
              file=sys.stderr)
        sys.exit(2)
    if names == ["probe"]:
        print(json.dumps(probe(), indent=2))
    else:
        try:
            result = fetch_models(names)
        except Exception as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        for path in result["installed"]:
            print(f"fetched {path}")
