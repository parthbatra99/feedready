#!/bin/sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE="$HOME/.cache/feedready"
SEGFORMER=0
MODELS=0
for arg in "$@"; do
  case "$arg" in
    --segformer) SEGFORMER=1 ;;
    --models) MODELS=1 ;;
    *) echo "usage: setup.sh [--segformer] [--models]" >&2; exit 2 ;;
  esac
done
mkdir -p "$CACHE/bin" "$CACHE/models"

VENV="$CACHE/venv"
if [ ! -x "$VENV/bin/python" ]; then
  if command -v uv >/dev/null; then
    uv venv --python 3.14 "$VENV"
  else
    PY=""
    for cand in python3.14 python3; do
      if command -v "$cand" >/dev/null && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 14))'; then
        PY="$cand"
        break
      fi
    done
    if [ -z "$PY" ]; then
      echo "feedready needs Python 3.14. Install uv (brew install uv, or https://docs.astral.sh/uv/) and rerun setup.sh." >&2
      exit 1
    fi
    "$PY" -m venv "$VENV"
  fi
fi
if command -v uv >/dev/null; then
  uv pip install -q --python "$VENV/bin/python" -r "$DIR/requirements.txt"
else
  "$VENV/bin/pip" install -q -r "$DIR/requirements.txt"
fi

if [ "$(uname)" = "Darwin" ]; then
  swiftc -O "$DIR/swift/feedready_engine.swift" -o "$CACHE/bin/feedready-engine"
  shasum -a 256 "$DIR/swift/feedready_engine.swift" | cut -d" " -f1 > "$CACHE/bin/feedready-engine.sha256"
fi

if [ "$SEGFORMER" = 1 ]; then
  "$VENV/bin/python" "$DIR/scripts/bootstrap.py" segformer
fi

if [ "$MODELS" = 1 ]; then
  "$VENV/bin/python" "$DIR/scripts/bootstrap.py" edgetam migan yunet u2netp
fi

"$DIR/run.sh" doctor
