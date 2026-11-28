#!/usr/bin/env sh
# cvprism bootstrap for macOS / Linux. Works from a git clone or a USB drive.
# Creates a venv in the user data dir (never on the USB drive), installs cvprism
# from this folder, then runs first-time setup (any arguments go to `cvprism init`).
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  return 1
}

PY="$(find_python)" || {
  echo "cvprism needs Python 3.10 or newer."
  case "$(uname -s)" in
    Darwin) echo "Install it with:  brew install python@3.12   (or from https://www.python.org/downloads/)";;
    *)      echo "Install it with your package manager, e.g.:  sudo apt install python3 python3-venv";;
  esac
  exit 1
}

if [ -n "${CVPRISM_HOME:-}" ]; then
  DATA="$CVPRISM_HOME"
elif [ "$(uname -s)" = "Darwin" ]; then
  DATA="$HOME/Library/Application Support/cvprism"
else
  DATA="${XDG_DATA_HOME:-$HOME/.local/share}/cvprism"
fi
VENV="$DATA/venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating environment in $VENV"
  mkdir -p "$DATA"
  "$PY" -m venv "$VENV"
fi

echo "Installing cvprism from $HERE"
if [ -d "$HERE/wheelhouse" ]; then
  "$VENV/bin/python" -m pip install -q --no-index --find-links "$HERE/wheelhouse" "$HERE[all]"     || "$VENV/bin/python" -m pip install -q --no-index --find-links "$HERE/wheelhouse" "$HERE"
else
  "$VENV/bin/python" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
  # PDF/DOCX renderers are optional extras; fall back to the core if they cannot be installed
  "$VENV/bin/python" -m pip install -q "$HERE[all]" || "$VENV/bin/python" -m pip install -q "$HERE"
fi

CVPRISM="$VENV/bin/cvprism"

# No arguments: set up in the browser, then open the app.
if [ "$#" -eq 0 ]; then
  if ! "$CVPRISM" status >/dev/null 2>&1; then
    "$CVPRISM" init --web || exit 1
  fi
  echo
  echo "Opening cvprism in your browser. Keep this window open while you use it."
  exec "$CVPRISM" app
fi

if "$CVPRISM" status >/dev/null 2>&1; then
  "$CVPRISM" status
else
  "$CVPRISM" init "$@"
fi

echo
echo "cvprism is installed at: $CVPRISM"
echo "Add it to your PATH, e.g.:  echo 'export PATH=\"$VENV/bin:\$PATH\"' >> ~/.profile"
