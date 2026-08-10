#!/usr/bin/env bash
# RemakeFace2API one-click deployment
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PORT="${PORT:-8610}"
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "[error] python3 not found. Please install Python 3.9+ first." >&2
  exit 1
fi

mkdir -p state server/data/generated examples

if [ ! -x .venv/bin/python ]; then
  echo "[1/3] Creating local virtual environment: .venv"
  if ! "$PYTHON" -m venv .venv; then
    echo "[error] Failed to create venv. On Debian/Ubuntu run: sudo apt update && sudo apt install -y python3-venv" >&2
    exit 1
  fi
else
  echo "[1/3] Reusing existing .venv"
fi

echo "[2/3] Installing/updating Python dependencies"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] Starting RemakeFace2API on 0.0.0.0:${PORT}"
echo "WebUI:  http://127.0.0.1:${PORT}/"
echo "Health: http://127.0.0.1:${PORT}/api/health"
exec .venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port "$PORT"
